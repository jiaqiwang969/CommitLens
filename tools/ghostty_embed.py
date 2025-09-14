#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Minimal libghostty embedding helper for macOS.

This uses ctypes to load a libghostty dynamic library and embed a surface
into an existing NSView pointer (we take the Tkinter frame's native view id).

Notes:
- Requires macOS and a built libghostty dynamic library (libghostty.dylib).
- We schedule ghostty_app_tick via the GUI main loop on wakeups.
- Clipboard hooks use the provided tkinter root for copy/paste.

Limitations:
- Action callbacks are stubbed; advanced features (open URL, etc.) are no-ops.
- Content scale detection is heuristic using Tk metrics; you can override.
"""

from __future__ import annotations

import ctypes as C
import os
import sys
from dataclasses import dataclass
from typing import Optional


# ---------------- ctypes types ----------------

class ghostty_runtime_config_s(C.Structure):
    _fields_ = [
        ("userdata", C.c_void_p),
        ("supports_selection_clipboard", C.c_bool),
        ("wakeup_cb", C.c_void_p),
        ("action_cb", C.c_void_p),
        ("read_clipboard_cb", C.c_void_p),
        ("confirm_read_clipboard_cb", C.c_void_p),
        ("write_clipboard_cb", C.c_void_p),
        ("close_surface_cb", C.c_void_p),
    ]


class ghostty_platform_macos_s(C.Structure):
    _fields_ = [("nsview", C.c_void_p)]


class ghostty_platform_ios_s(C.Structure):
    _fields_ = [("uiview", C.c_void_p)]


class ghostty_platform_u(C.Union):
    _fields_ = [
        ("macos", ghostty_platform_macos_s),
        ("ios", ghostty_platform_ios_s),
    ]


class ghostty_surface_config_s(C.Structure):
    _fields_ = [
        ("platform_tag", C.c_int),
        ("platform", ghostty_platform_u),
        ("userdata", C.c_void_p),
        ("scale_factor", C.c_double),
        ("font_size", C.c_float),
        ("working_directory", C.c_char_p),
        ("command", C.c_char_p),
        ("env_vars", C.c_void_p),
        ("env_var_count", C.c_size_t),
        ("initial_input", C.c_char_p),
        ("wait_after_command", C.c_bool),
    ]


class ghostty_surface_size_s(C.Structure):
    _fields_ = [
        ("columns", C.c_uint16),
        ("rows", C.c_uint16),
        ("width_px", C.c_uint32),
        ("height_px", C.c_uint32),
        ("cell_width_px", C.c_uint32),
        ("cell_height_px", C.c_uint32),
    ]


# enums/constants
GHOSTTY_PLATFORM_INVALID = 0
GHOSTTY_PLATFORM_MACOS = 1
GHOSTTY_PLATFORM_IOS = 2

# clipboards
GHOSTTY_CLIPBOARD_STANDARD = 0
GHOSTTY_CLIPBOARD_SELECTION = 1


# ---------------- Wrapper ----------------

def _default_lib_path() -> Optional[str]:
    # Prefer explicit env var
    p = os.environ.get("LIBGHOSTTY_PATH")
    if p and os.path.exists(p):
        return p
    # Try typical zig out location within repo
    guesses = [
        os.path.join("ghostty", "zig-out", "lib", "libghostty.dylib"),
        os.path.join("zig-out", "lib", "libghostty.dylib"),
    ]
    for g in guesses:
        if os.path.exists(g):
            return g
    return None


@dataclass
class GhosttyHandles:
    lib: C.CDLL
    app: C.c_void_p
    surface: C.c_void_p


class GhosttyEmbedder:
    def __init__(self, tk_root) -> None:
        self._tk_root = tk_root
        self._handles: Optional[GhosttyHandles] = None
        self._tick_pending = False
        self._ns_host_view = None  # PyObjC NSView hosting Metal layer

    def _load_lib(self, path: Optional[str] = None) -> C.CDLL:
        lp = path or _default_lib_path()
        if not lp:
            raise RuntimeError("未找到 libghostty.dylib，请先构建并设置 LIBGHOSTTY_PATH 或使用 zig-out/lib。")
        lib = C.CDLL(lp)

        # Signatures
        lib.ghostty_init.argtypes = (C.c_size_t, C.POINTER(C.c_char_p))
        lib.ghostty_init.restype = C.c_int

        lib.ghostty_config_new.argtypes = ()
        lib.ghostty_config_new.restype = C.c_void_p
        lib.ghostty_config_load_default_files.argtypes = (C.c_void_p,)
        lib.ghostty_config_finalize.argtypes = (C.c_void_p,)

        lib.ghostty_app_new.argtypes = (C.POINTER(ghostty_runtime_config_s), C.c_void_p)
        lib.ghostty_app_new.restype = C.c_void_p
        lib.ghostty_app_tick.argtypes = (C.c_void_p,)

        lib.ghostty_surface_config_new.argtypes = ()
        lib.ghostty_surface_config_new.restype = ghostty_surface_config_s
        lib.ghostty_surface_new.argtypes = (C.c_void_p, C.POINTER(ghostty_surface_config_s))
        lib.ghostty_surface_new.restype = C.c_void_p
        lib.ghostty_surface_set_size.argtypes = (C.c_void_p, C.c_uint32, C.c_uint32)
        lib.ghostty_surface_set_content_scale.argtypes = (C.c_void_p, C.c_double, C.c_double)
        lib.ghostty_surface_set_focus.argtypes = (C.c_void_p, C.c_bool)
        lib.ghostty_surface_text.argtypes = (C.c_void_p, C.c_char_p, C.c_size_t)

        # Clipboard completion API
        lib.ghostty_surface_complete_clipboard_request.argtypes = (
            C.c_void_p, C.c_char_p, C.c_void_p, C.c_bool
        )

        return lib

    # ---- callbacks from libghostty ----
    def _cb_wakeup(self, _userdata):
        # schedule a tick on main thread
        if not self._tick_pending and self._handles:
            self._tick_pending = True
            self._tk_root.after(0, self._tick)

    def _tick(self):
        try:
            if not self._handles:
                return
            self._handles.lib.ghostty_app_tick(self._handles.app)
        finally:
            self._tick_pending = False

    def _cb_action(self, app, target, action):  # no-op stub
        # Return true to indicate handled; simple stub.
        return True

    def _cb_read_clipboard(self, userdata, clipboard_kind, req_ptr):
        # clipboard_kind: int
        try:
            text = self._tk_safe_clipboard_get()
        except Exception:
            text = ""  # empty
        if self._handles:
            self._handles.lib.ghostty_surface_complete_clipboard_request(
                self._handles.surface, text.encode("utf-8"), req_ptr, False
            )

    def _cb_confirm_read_clipboard(self, userdata, text_ptr, req_ptr, req_kind):
        # Trust and complete
        if self._handles:
            self._handles.lib.ghostty_surface_complete_clipboard_request(
                self._handles.surface, C.cast(C.c_char_p, text_ptr), req_ptr, True
            )

    def _cb_write_clipboard(self, userdata, text_ptr, clipboard_kind, confirm):
        try:
            text = C.cast(text_ptr, C.c_char_p).value.decode("utf-8")
            self._tk_root.clipboard_clear()
            self._tk_root.clipboard_append(text)
        except Exception:
            pass

    def _cb_close_surface(self, userdata, _confirm_quit):
        # Surface asked to close; free handles
        self.free()

    def _tk_safe_clipboard_get(self) -> str:
        try:
            return self._tk_root.clipboard_get()
        except Exception:
            return ""

    # ---- public API ----
    def embed_into_tk(self, frame_widget, working_dir: Optional[str] = None, lib_path: Optional[str] = None):
        # 1) load lib
        lib = self._load_lib(lib_path)
        # 2) init (ensure autorelease pool)
        try:
            from Foundation import NSAutoreleasePool
            pool = NSAutoreleasePool.alloc().init()
        except Exception:
            pool = None
        lib.ghostty_init(0, None)
        # 3) config
        cfg = lib.ghostty_config_new()
        lib.ghostty_config_load_default_files(cfg)
        lib.ghostty_config_finalize(cfg)

        # 4) runtime callbacks
        WakeupCB = C.CFUNCTYPE(None, C.c_void_p)
        ActionCB = C.CFUNCTYPE(C.c_bool, C.c_void_p, C.c_void_p, C.c_void_p)
        ReadCB = C.CFUNCTYPE(None, C.c_void_p, C.c_int, C.c_void_p)
        ConfirmReadCB = C.CFUNCTYPE(None, C.c_void_p, C.c_char_p, C.c_void_p, C.c_int)
        WriteCB = C.CFUNCTYPE(None, C.c_void_p, C.c_char_p, C.c_int, C.c_bool)
        CloseCB = C.CFUNCTYPE(None, C.c_void_p, C.c_bool)

        self._cb_wakeup_c = WakeupCB(self._cb_wakeup)
        self._cb_action_c = ActionCB(self._cb_action)
        self._cb_read_c = ReadCB(self._cb_read_clipboard)
        self._cb_confirm_c = ConfirmReadCB(self._cb_confirm_read_clipboard)
        self._cb_write_c = WriteCB(self._cb_write_clipboard)
        self._cb_close_c = CloseCB(self._cb_close_surface)

        runtime = ghostty_runtime_config_s()
        runtime.userdata = None
        runtime.supports_selection_clipboard = False
        runtime.wakeup_cb = C.cast(self._cb_wakeup_c, C.c_void_p)
        runtime.action_cb = C.cast(self._cb_action_c, C.c_void_p)
        runtime.read_clipboard_cb = C.cast(self._cb_read_c, C.c_void_p)
        runtime.confirm_read_clipboard_cb = C.cast(self._cb_confirm_c, C.c_void_p)
        runtime.write_clipboard_cb = C.cast(self._cb_write_c, C.c_void_p)
        runtime.close_surface_cb = C.cast(self._cb_close_c, C.c_void_p)

        app = lib.ghostty_app_new(C.byref(runtime), cfg)
        if not app:
            raise RuntimeError("ghostty_app_new 失败")

        # 5) surface
        # Create a dedicated NSView subview positioned to overlay the Tk frame (PyObjC required)
        nsview_ptr = self._ensure_host_nsview(frame_widget)
        if not nsview_ptr:
            raise RuntimeError("未能获取有效的 NSView（请先安装 PyObjC: pip install pyobjc）")
        sfcfg = lib.ghostty_surface_config_new()
        sfcfg.platform_tag = GHOSTTY_PLATFORM_MACOS
        sfcfg.platform.macos.nsview = C.c_void_p(nsview_ptr)
        sfcfg.userdata = None
        sfcfg.scale_factor = float(self.suggest_scale(frame_widget))
        sfcfg.font_size = 0.0
        sfcfg.working_directory = (working_dir or os.getcwd()).encode("utf-8")
        sfcfg.command = None
        sfcfg.env_vars = None
        sfcfg.env_var_count = 0
        sfcfg.initial_input = None
        sfcfg.wait_after_command = False

        surface = lib.ghostty_surface_new(app, C.byref(sfcfg))
        if not surface:
            raise RuntimeError("ghostty_surface_new 失败")

        # 6) set size + focus
        w = max(1, frame_widget.winfo_width())
        h = max(1, frame_widget.winfo_height())
        lib.ghostty_surface_set_size(surface, w, h)
        lib.ghostty_surface_set_content_scale(surface, sfcfg.scale_factor, sfcfg.scale_factor)
        lib.ghostty_surface_set_focus(surface, True)

        self._handles = GhosttyHandles(lib=lib, app=app, surface=surface)

        # initial tick
        self._tk_root.after(0, self._tick)
        if pool is not None:
            try:
                pool.drain()
            except Exception:
                pass

    def update_size(self, width: int, height: int):
        if self._handles:
            self._handles.lib.ghostty_surface_set_size(self._handles.surface, int(width), int(height))
        self._update_host_nsview_frame()

    def update_scale(self, scale: float):
        if self._handles:
            self._handles.lib.ghostty_surface_set_content_scale(self._handles.surface, float(scale), float(scale))

    def free(self):
        # Note: libghostty has free APIs but we keep it simple; let process exit handle.
        self._handles = None

    @staticmethod
    def suggest_scale(widget) -> float:
        try:
            # Heuristic: points-per-inch reported by Tk divided by 72
            # gives approximate pixel scale factor on macOS.
            ppi = float(widget.winfo_fpixels("1i"))
            scale = max(1.0, ppi / 72.0)
            return round(scale, 2)
        except Exception:
            return 1.0

    def send_text(self, text: str):
        if not self._handles:
            return
        if not text:
            return
        b = text.encode("utf-8", errors="ignore")
        self._handles.lib.ghostty_surface_text(self._handles.surface, b, len(b))

    # ---------- PyObjC host view helpers ----------
    def _ensure_host_nsview(self, frame_widget) -> Optional[int]:
        try:
            import objc
            from AppKit import NSApp, NSView, NSScreen, NSMakeRect
        except Exception:
            return None

        # Get target window and contentView
        app = NSApp()
        window = app.keyWindow() or app.mainWindow()
        if window is None:
            return None
        content_view = window.contentView()

        # Build or reuse host view
        if self._ns_host_view is None:
            # Create empty NSView; libghostty will attach CAMetalLayer to it
            rect = ((0.0, 0.0), (100.0, 100.0))
            host = NSView.alloc().initWithFrame_(rect)
            host.setWantsLayer_(True)
            content_view.addSubview_(host)
            self._ns_host_view = host

        # Position/size the host view to overlay the Tk frame
        self._place_nsview_over_tk(frame_widget)

        # Return raw pointer for libghostty
        import objc as _objc
        return int(_objc.pyobjc_id(self._ns_host_view))

    def _place_nsview_over_tk(self, frame_widget):
        try:
            import objc
            from AppKit import NSApp, NSScreen, NSMakeRect
        except Exception:
            return
        app = NSApp()
        window = app.keyWindow() or app.mainWindow()
        if window is None or self._ns_host_view is None:
            return
        # Screen rect (Tk gives top-left origin coords)
        x = frame_widget.winfo_rootx()
        y_top = frame_widget.winfo_rooty()
        w = frame_widget.winfo_width()
        h = frame_widget.winfo_height()
        # Convert to Cocoa screen (bottom-left) rect
        main_screen = NSScreen.mainScreen()
        screen_frame = main_screen.frame()
        y_bl = screen_frame.size.height - (y_top + h)
        screen_rect = NSMakeRect(x, y_bl, w, h)
        # Convert to window coordinates
        win_rect = window.convertRectFromScreen_(screen_rect)
        # Set as frame
        self._ns_host_view.setFrame_(win_rect)

    def _update_host_nsview_frame(self):
        # Reposition host view to follow Tk frame
        if self._ns_host_view is None:
            return
        try:
            # Assume we stored the tk frame as last used via closure; not stored, so no-op.
            # Callers should pass frame_widget to _place_nsview_over_tk directly when size changes.
            pass
        except Exception:
            pass
