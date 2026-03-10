#!/usr/bin/env python3
"""
Windows desktop capture MCP.

Focused on deterministic window listing/activation/capture for desktop apps
such as Power BI Desktop.
"""

from __future__ import annotations

import argparse
import ctypes
import ctypes.wintypes as wt
import json
import os
import pathlib
import subprocess
import sys
import tempfile
import time
from dataclasses import asdict, dataclass
from typing import Any, Dict, List, Optional, Tuple

import win32con
import win32gui
import win32process
import win32ui
from mcp.server.fastmcp import FastMCP


mcp = FastMCP("windows-capture")

SCRIPT_DIR = pathlib.Path(__file__).resolve().parent
KERNEL32 = ctypes.WinDLL("kernel32", use_last_error=True)
USER32 = ctypes.WinDLL("user32", use_last_error=True)

PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
PW_RENDERFULLCONTENT = 0x00000002
SW_RESTORE = 9


class RECT(ctypes.Structure):
    _fields_ = [
        ("left", wt.LONG),
        ("top", wt.LONG),
        ("right", wt.LONG),
        ("bottom", wt.LONG),
    ]


class POINT(ctypes.Structure):
    _fields_ = [("x", wt.LONG), ("y", wt.LONG)]


QueryFullProcessImageNameW = KERNEL32.QueryFullProcessImageNameW
QueryFullProcessImageNameW.argtypes = [
    wt.HANDLE,
    wt.DWORD,
    wt.LPWSTR,
    ctypes.POINTER(wt.DWORD),
]
QueryFullProcessImageNameW.restype = wt.BOOL

OpenProcess = KERNEL32.OpenProcess
OpenProcess.argtypes = [wt.DWORD, wt.BOOL, wt.DWORD]
OpenProcess.restype = wt.HANDLE

CloseHandle = KERNEL32.CloseHandle
CloseHandle.argtypes = [wt.HANDLE]
CloseHandle.restype = wt.BOOL

PrintWindow = USER32.PrintWindow
PrintWindow.argtypes = [wt.HWND, wt.HDC, wt.UINT]
PrintWindow.restype = wt.BOOL

GetClientRect = USER32.GetClientRect
GetClientRect.argtypes = [wt.HWND, ctypes.POINTER(RECT)]
GetClientRect.restype = wt.BOOL

ClientToScreen = USER32.ClientToScreen
ClientToScreen.argtypes = [wt.HWND, ctypes.POINTER(POINT)]
ClientToScreen.restype = wt.BOOL


@dataclass
class WindowInfo:
    hwnd: int
    title: str
    process_name: str
    pid: int
    bounds: Dict[str, int]
    client_bounds: Optional[Dict[str, int]]
    is_visible: bool
    is_minimized: bool


def _normalize_text(value: Optional[str]) -> str:
    return (value or "").strip()


def _safe_basename(path_value: str) -> str:
    return os.path.basename(path_value) if path_value else ""


def _get_process_name(pid: int) -> str:
    handle = OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not handle:
        return ""
    try:
        size = wt.DWORD(32768)
        buf = ctypes.create_unicode_buffer(size.value)
        if QueryFullProcessImageNameW(handle, 0, buf, ctypes.byref(size)):
            return _safe_basename(buf.value)
        return ""
    finally:
        CloseHandle(handle)


def _window_bounds(hwnd: int) -> Optional[Dict[str, int]]:
    try:
        left, top, right, bottom = win32gui.GetWindowRect(hwnd)
    except win32gui.error:
        return None
    return {
        "left": left,
        "top": top,
        "right": right,
        "bottom": bottom,
        "width": max(0, right - left),
        "height": max(0, bottom - top),
    }


def _client_bounds(hwnd: int) -> Optional[Dict[str, int]]:
    rect = RECT()
    if not GetClientRect(hwnd, ctypes.byref(rect)):
        return None
    origin = POINT(rect.left, rect.top)
    if not ClientToScreen(hwnd, ctypes.byref(origin)):
        return None
    width = max(0, rect.right - rect.left)
    height = max(0, rect.bottom - rect.top)
    return {
        "left": origin.x,
        "top": origin.y,
        "right": origin.x + width,
        "bottom": origin.y + height,
        "width": width,
        "height": height,
    }


def list_windows_data(
    process_name: str = "",
    title_contains: str = "",
    only_visible: bool = True,
) -> List[WindowInfo]:
    process_name = _normalize_text(process_name).lower()
    title_contains = _normalize_text(title_contains).lower()
    windows: List[WindowInfo] = []

    def _cb(hwnd: int, _: Any) -> bool:
        title = _normalize_text(win32gui.GetWindowText(hwnd))
        visible = bool(win32gui.IsWindowVisible(hwnd))
        minimized = bool(win32gui.IsIconic(hwnd))
        if only_visible and not visible:
            return True
        if not title:
            return True

        _, pid = win32process.GetWindowThreadProcessId(hwnd)
        proc = _get_process_name(pid)

        if process_name and process_name not in proc.lower():
            return True
        if title_contains and title_contains not in title.lower():
            return True

        bounds = _window_bounds(hwnd)
        if not bounds or bounds["width"] <= 0 or bounds["height"] <= 0:
            return True

        windows.append(
            WindowInfo(
                hwnd=hwnd,
                title=title,
                process_name=proc,
                pid=pid,
                bounds=bounds,
                client_bounds=_client_bounds(hwnd),
                is_visible=visible,
                is_minimized=minimized,
            )
        )
        return True

    win32gui.EnumWindows(_cb, None)
    windows.sort(key=lambda w: (w.process_name.lower(), w.title.lower()))
    return windows


def _find_window(hwnd: int = 0, title_contains: str = "", process_name: str = "") -> WindowInfo:
    windows = list_windows_data(process_name=process_name, title_contains=title_contains, only_visible=False)
    if hwnd:
        matches = [w for w in windows if w.hwnd == hwnd]
        if not matches:
            raise ValueError(f"No se encontró una ventana con hwnd={hwnd}.")
        return matches[0]

    if not title_contains and not process_name:
        raise ValueError("Debes indicar hwnd, title_contains o process_name.")

    if not windows:
        raise ValueError("No se encontraron ventanas que coincidan con el filtro.")
    preferred = [
        w
        for w in windows
        if w.is_visible and not w.is_minimized and w.bounds["width"] >= 200 and w.bounds["height"] >= 150
    ]
    if len(preferred) == 1:
        return preferred[0]
    if len(preferred) > 1:
        windows = preferred
    if len(windows) > 1:
        sample = [f"{w.hwnd} | {w.process_name} | {w.title}" for w in windows[:5]]
        raise ValueError(
            "Hay múltiples ventanas coincidentes. Refina el filtro o usa hwnd. Coincidencias: "
            + " ; ".join(sample)
        )
    return windows[0]


def activate_window_data(hwnd: int = 0, title_contains: str = "", process_name: str = "") -> Dict[str, Any]:
    window = _find_window(hwnd=hwnd, title_contains=title_contains, process_name=process_name)
    warning = ""
    activation_succeeded = True
    try:
        win32gui.ShowWindow(window.hwnd, SW_RESTORE)
        time.sleep(0.2)
        win32gui.SetForegroundWindow(window.hwnd)
        time.sleep(0.4)
    except Exception as exc:
        # Windows can reject SetForegroundWindow depending on focus rules.
        # Treat activation as best-effort so capture can continue.
        activation_succeeded = False
        warning = str(exc) or "SetForegroundWindow falló sin detalle."
    refreshed = _find_window(hwnd=window.hwnd)
    return {
        "activated": activation_succeeded,
        "warning": warning,
        "window": asdict(refreshed),
    }


def _ensure_output_path(output_path: str = "", mode: str = "temp") -> pathlib.Path:
    if output_path:
        out = pathlib.Path(os.path.expandvars(output_path)).expanduser()
        if out.suffix.lower() != ".png":
            out = out.with_suffix(".png")
        out.parent.mkdir(parents=True, exist_ok=True)
        return out

    if mode == "temp":
        return pathlib.Path(tempfile.gettempdir()) / f"windows-capture-{int(time.time() * 1000)}.png"

    raise ValueError("output_path es obligatorio cuando mode != 'temp'.")


def _run_powershell(command: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            "C:\\WINDOWS\\System32\\WindowsPowerShell\\v1.0\\powershell.exe",
            "-NoProfile",
            "-NonInteractive",
            "-Command",
            command,
        ],
        capture_output=True,
        text=True,
        check=False,
    )


def _ps_string(value: str) -> str:
    return value.replace("'", "''")


def _capture_region_to_png(bounds: Dict[str, int], output_file: pathlib.Path) -> None:
    x = bounds["left"]
    y = bounds["top"]
    w = bounds["width"]
    h = bounds["height"]
    ps = (
        "Add-Type -AssemblyName System.Windows.Forms; "
        "Add-Type -AssemblyName System.Drawing; "
        f"$bmp = New-Object System.Drawing.Bitmap({w}, {h}); "
        "$g = [System.Drawing.Graphics]::FromImage($bmp); "
        f"$src = New-Object System.Drawing.Point({x}, {y}); "
        "$target = [System.Drawing.Point]::Empty; "
        f"$size = New-Object System.Drawing.Size({w}, {h}); "
        "$g.CopyFromScreen($src, $target, $size); "
        f"$bmp.Save('{_ps_string(str(output_file))}', [System.Drawing.Imaging.ImageFormat]::Png); "
        "$g.Dispose(); "
        "$bmp.Dispose();"
    )
    result = _run_powershell(ps)
    if result.returncode != 0 or not output_file.exists():
        raise RuntimeError(
            "Falló la captura por región. "
            + (result.stderr.strip() or result.stdout.strip() or "PowerShell no devolvió detalle.")
        )


def _convert_bmp_to_png(bmp_file: pathlib.Path, output_file: pathlib.Path) -> None:
    ps = (
        "Add-Type -AssemblyName System.Drawing; "
        f"$img = [System.Drawing.Image]::FromFile('{_ps_string(str(bmp_file))}'); "
        f"$img.Save('{_ps_string(str(output_file))}', [System.Drawing.Imaging.ImageFormat]::Png); "
        "$img.Dispose();"
    )
    result = _run_powershell(ps)
    if result.returncode != 0 or not output_file.exists():
        raise RuntimeError(
            "Falló la conversión BMP->PNG. "
            + (result.stderr.strip() or result.stdout.strip() or "PowerShell no devolvió detalle.")
        )


def _bitmap_is_mostly_blank(bitmap: win32ui.CreateBitmap) -> bool:
    info = bitmap.GetInfo()
    bits = bitmap.GetBitmapBits(True)
    if not bits:
        return True
    sample = bits[: min(len(bits), 40000)]
    unique = len(set(sample))
    if unique <= 2:
        return True
    non_zero = sum(1 for b in sample if b != 0)
    return non_zero < max(10, len(sample) // 200)


def _capture_printwindow_to_png(hwnd: int, output_file: pathlib.Path) -> Tuple[bool, str]:
    left, top, right, bottom = win32gui.GetWindowRect(hwnd)
    width = right - left
    height = bottom - top
    if width <= 0 or height <= 0:
        return False, "Window bounds inválidos."

    hwnd_dc = win32gui.GetWindowDC(hwnd)
    if not hwnd_dc:
        return False, "No se pudo obtener el DC de la ventana."

    temp_bmp = pathlib.Path(tempfile.gettempdir()) / f"windows-capture-{int(time.time() * 1000)}.bmp"
    mfc_dc = save_dc = bmp = None
    try:
        mfc_dc = win32ui.CreateDCFromHandle(hwnd_dc)
        save_dc = mfc_dc.CreateCompatibleDC()
        bmp = win32ui.CreateBitmap()
        bmp.CreateCompatibleBitmap(mfc_dc, width, height)
        save_dc.SelectObject(bmp)
        ok = PrintWindow(hwnd, save_dc.GetSafeHdc(), PW_RENDERFULLCONTENT)
        if not ok or _bitmap_is_mostly_blank(bmp):
            return False, "PrintWindow devolvió imagen vacía o falló."
        bmp.SaveBitmapFile(save_dc, str(temp_bmp))
        _convert_bmp_to_png(temp_bmp, output_file)
        return True, "printwindow"
    finally:
        try:
            if bmp:
                win32gui.DeleteObject(bmp.GetHandle())
        except Exception:
            pass
        try:
            if save_dc:
                save_dc.DeleteDC()
        except Exception:
            pass
        try:
            if mfc_dc:
                mfc_dc.DeleteDC()
        except Exception:
            pass
        try:
            win32gui.ReleaseDC(hwnd, hwnd_dc)
        except Exception:
            pass
        try:
            if temp_bmp.exists():
                temp_bmp.unlink()
        except Exception:
            pass


def capture_window_data(
    hwnd: int = 0,
    title_contains: str = "",
    process_name: str = "",
    client_only: bool = False,
    bring_to_front: bool = True,
    output_path: str = "",
    mode: str = "temp",
) -> Dict[str, Any]:
    window = _find_window(hwnd=hwnd, title_contains=title_contains, process_name=process_name)
    activation_info: Dict[str, Any] = {}
    if bring_to_front:
        activation_info = activate_window_data(hwnd=window.hwnd)
        window = _find_window(hwnd=window.hwnd)

    out = _ensure_output_path(output_path=output_path, mode=mode)

    method = "screen-grab"
    fallback_reason = ""
    if not client_only:
        ok, detail = _capture_printwindow_to_png(window.hwnd, out)
        if ok:
            method = detail
        else:
            fallback_reason = detail
            bounds = window.bounds
            _capture_region_to_png(bounds, out)
    else:
        bounds = window.client_bounds or window.bounds
        _capture_region_to_png(bounds, out)

    return {
        "path": str(out),
        "capture_method": method,
        "fallback_reason": fallback_reason,
        "client_only": client_only,
        "activation": activation_info,
        "window": asdict(window),
    }


def capture_region_data(
    x: int,
    y: int,
    width: int,
    height: int,
    output_path: str = "",
    mode: str = "temp",
) -> Dict[str, Any]:
    if width <= 0 or height <= 0:
        raise ValueError("width y height deben ser positivos.")
    out = _ensure_output_path(output_path=output_path, mode=mode)
    bounds = {"left": x, "top": y, "width": width, "height": height}
    _capture_region_to_png(bounds, out)
    return {"path": str(out), "bounds": bounds, "capture_method": "screen-grab"}


def foreground_window_data() -> Dict[str, Any]:
    hwnd = win32gui.GetForegroundWindow()
    if not hwnd:
        raise ValueError("No hay ventana activa en primer plano.")
    return {"window": asdict(_find_window(hwnd=hwnd))}


@mcp.tool()
def windows_list_windows(
    process_name: str = "",
    title_contains: str = "",
    only_visible: bool = True,
) -> str:
    """Lista ventanas de Windows con hwnd, título, proceso y bounds."""
    windows = [
        asdict(w)
        for w in list_windows_data(
            process_name=process_name,
            title_contains=title_contains,
            only_visible=only_visible,
        )
    ]
    return json.dumps({"count": len(windows), "windows": windows}, ensure_ascii=False, indent=2)


@mcp.tool()
def windows_activate_window(
    hwnd: int = 0,
    title_contains: str = "",
    process_name: str = "",
) -> str:
    """Activa una ventana por hwnd, título parcial o nombre de proceso."""
    return json.dumps(
        activate_window_data(hwnd=hwnd, title_contains=title_contains, process_name=process_name),
        ensure_ascii=False,
        indent=2,
    )


@mcp.tool()
def windows_capture_window(
    hwnd: int = 0,
    title_contains: str = "",
    process_name: str = "",
    client_only: bool = False,
    bring_to_front: bool = True,
    output_path: str = "",
    mode: str = "temp",
) -> str:
    """Captura una ventana específica y guarda PNG. Usa PrintWindow y fallback de screen-grab."""
    return json.dumps(
        capture_window_data(
            hwnd=hwnd,
            title_contains=title_contains,
            process_name=process_name,
            client_only=client_only,
            bring_to_front=bring_to_front,
            output_path=output_path,
            mode=mode,
        ),
        ensure_ascii=False,
        indent=2,
    )


@mcp.tool()
def windows_capture_region(
    x: int,
    y: int,
    width: int,
    height: int,
    output_path: str = "",
    mode: str = "temp",
) -> str:
    """Captura una región del escritorio y guarda PNG."""
    return json.dumps(
        capture_region_data(
            x=x,
            y=y,
            width=width,
            height=height,
            output_path=output_path,
            mode=mode,
        ),
        ensure_ascii=False,
        indent=2,
    )


@mcp.tool()
def windows_get_foreground_window() -> str:
    """Devuelve metadata de la ventana activa."""
    return json.dumps(foreground_window_data(), ensure_ascii=False, indent=2)


@mcp.tool()
def powerbi_list_desktop_windows(title_contains: str = "") -> str:
    """Lista solo ventanas visibles de Power BI Desktop."""
    return windows_list_windows(process_name="PBIDesktop.exe", title_contains=title_contains, only_visible=True)


@mcp.tool()
def powerbi_activate_report_window(title_contains: str = "analisis_disponibilidad") -> str:
    """Activa una ventana de Power BI Desktop por título parcial."""
    return windows_activate_window(process_name="PBIDesktop.exe", title_contains=title_contains)


@mcp.tool()
def powerbi_capture_report_window(
    title_contains: str = "analisis_disponibilidad",
    client_only: bool = False,
    bring_to_front: bool = True,
    output_path: str = "",
    mode: str = "temp",
) -> str:
    """Captura la ventana del reporte de Power BI Desktop."""
    return windows_capture_window(
        process_name="PBIDesktop.exe",
        title_contains=title_contains,
        client_only=client_only,
        bring_to_front=bring_to_front,
        output_path=output_path,
        mode=mode,
    )


def _self_test(title_contains: str, output_path: str = "") -> int:
    windows = list_windows_data(title_contains=title_contains, only_visible=False)
    if not windows:
        print(f"No se encontraron ventanas con title_contains={title_contains!r}", file=sys.stderr)
        return 1
    target = windows[0]
    print(json.dumps({"selected_window": asdict(target)}, ensure_ascii=False, indent=2))
    result = capture_window_data(hwnd=target.hwnd, bring_to_front=True, output_path=output_path, mode="temp")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Windows capture MCP server")
    parser.add_argument("--self-test", action="store_true", help="Run a local self-test instead of MCP stdio")
    parser.add_argument("--title", default="analisis_disponibilidad", help="Title filter for --self-test")
    parser.add_argument("--output-path", default="", help="Optional output path for --self-test")
    args = parser.parse_args()

    if args.self_test:
        raise SystemExit(_self_test(args.title, args.output_path))

    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
