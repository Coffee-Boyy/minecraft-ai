"""Screen capture module for capturing Minecraft frames."""

import base64
import json
import os
import subprocess
import time
from io import BytesIO
from typing import Literal, Optional

import cv2
import mss
import numpy as np
from PIL import Image

try:
    import pyscreenshot as ImageGrab
    HAS_PYSCREENSHOT = True
except ImportError:
    HAS_PYSCREENSHOT = False

# For cross-platform window detection (works on both X11 and Wayland)
try:
    import pywinctl
    HAS_PYWINCTL = True
except ImportError:
    HAS_PYWINCTL = False

# For X11-only window detection (fallback)
try:
    from Xlib import X, display as xlib_display
    from Xlib.error import XError
    HAS_XLIB = True
except ImportError:
    HAS_XLIB = False


class ScreenCapture:
    """Captures screenshots from the screen or a specific window."""

    def __init__(
        self,
        mode: Literal["screen", "window"] = "screen",
        target_resolution: tuple[int, int] = (854, 480),
        monitor_index: int = 1,
        window_title: str = "Minecraft",
    ):
        """
        Initialize the screen capture.

        Args:
            mode: Capture mode - 'screen' for full screen, 'window' for specific window
            target_resolution: Target resolution (width, height) for captured frames
            monitor_index: Monitor index to capture from (1-indexed)
            window_title: Window title to search for when mode='window' (case-insensitive substring match)
        """
        self.mode = mode
        self.target_resolution = target_resolution
        self.monitor_index = monitor_index
        self.window_title = window_title
        self._last_capture_time = 0.0
        self._window_region = None
        self._xlib_display = None
        self._pywinctl_window = None

        # Detect if running on Wayland
        self.is_wayland = os.environ.get("XDG_SESSION_TYPE", "").lower() == "wayland"

        if self.is_wayland and not HAS_PYSCREENSHOT:
            raise RuntimeError(
                "Running on Wayland but pyscreenshot is not installed. "
                "Install with: pip install pyscreenshot"
            )

        # Check window capture support
        if self.mode == "window" and not HAS_PYWINCTL:
            print("Warning: pywinctl not installed. Window capture disabled, using full screen.")
            self.mode = "screen"

        # Use mss only on X11, pyscreenshot on Wayland
        if not self.is_wayland:
            self.sct = mss.mss(with_cursor=False)
            # Initialize X11 display for window finding (legacy fallback)
            if self.mode == "window" and HAS_XLIB and not HAS_PYWINCTL:
                try:
                    self._xlib_display = xlib_display.Display()
                except Exception as e:
                    print(f"Warning: Could not connect to X11 display: {e}")
            print("Detected X11 - using mss backend")
        else:
            self.sct = None
            if self.mode == "window":
                print("Detected Wayland - window capture enabled via GNOME Shell API")
            else:
                print("Detected Wayland - using pyscreenshot backend")

    def _get_wayland_windows(self) -> list:
        """
        Get list of windows on Wayland via GNOME Shell D-Bus API.

        Returns:
            List of window dictionaries with title, class, and geometry info
        """
        try:
            # Use wmctrl if available (works on some Wayland compositors)
            result = subprocess.run(
                ['wmctrl', '-lG'],
                capture_output=True,
                text=True,
                timeout=2
            )

            if result.returncode == 0:
                windows = []
                for line in result.stdout.strip().split('\n'):
                    if not line:
                        continue
                    parts = line.split(None, 7)
                    if len(parts) >= 8:
                        windows.append({
                            'left': int(parts[2]),
                            'top': int(parts[3]),
                            'width': int(parts[4]),
                            'height': int(parts[5]),
                            'title': parts[7]
                        })
                return windows
        except (subprocess.TimeoutExpired, FileNotFoundError, Exception):
            pass

        # If wmctrl fails, try xdotool (works on XWayland windows)
        try:
            result = subprocess.run(
                ['xdotool', 'search', '--name', self.window_title],
                capture_output=True,
                text=True,
                timeout=2
            )

            if result.returncode == 0 and result.stdout.strip():
                window_id = result.stdout.strip().split('\n')[0]

                # Get window geometry
                geom_result = subprocess.run(
                    ['xdotool', 'getwindowgeometry', '--shell', window_id],
                    capture_output=True,
                    text=True,
                    timeout=2
                )

                if geom_result.returncode == 0:
                    geom_data = {}
                    for line in geom_result.stdout.strip().split('\n'):
                        if '=' in line:
                            key, value = line.split('=', 1)
                            geom_data[key] = value

                    return [{
                        'left': int(geom_data.get('X', 0)),
                        'top': int(geom_data.get('Y', 0)),
                        'width': int(geom_data.get('WIDTH', 800)),
                        'height': int(geom_data.get('HEIGHT', 600)),
                        'title': self.window_title
                    }]
        except (subprocess.TimeoutExpired, FileNotFoundError, Exception):
            pass

        return []

    def _find_window_region(self) -> Optional[dict]:
        """
        Find the Minecraft window and return its region.

        Returns:
            Dictionary with 'left', 'top', 'width', 'height' keys, or None if not found
        """
        # On Wayland, try alternative methods
        if self.is_wayland:
            # Try to get windows via wmctrl or xdotool
            windows = self._get_wayland_windows()
            window_title_lower = self.window_title.lower()

            for window in windows:
                if window.get('title') and window_title_lower in window['title'].lower():
                    return {
                        'left': window['left'],
                        'top': window['top'],
                        'width': window['width'],
                        'height': window['height'],
                    }

            return None

        # Try pywinctl first (works on X11)
        if HAS_PYWINCTL and not self.is_wayland:
            # Only use pywinctl on X11 - it's unreliable on Wayland
            try:
                window_title_lower = self.window_title.lower()

                # Get all windows
                all_windows = pywinctl.getAllWindows()

                # Search for window with matching title
                for window in all_windows:
                    if window.title and window_title_lower in window.title.lower():
                        # Cache the window object for potential future use
                        self._pywinctl_window = window

                        # Get window geometry
                        bbox = window.bbox
                        return {
                            'left': bbox.left,
                            'top': bbox.top,
                            'width': bbox.width,
                            'height': bbox.height,
                        }

                return None

            except Exception as e:
                print(f"Warning: Error finding window with pywinctl: {e}")
                # Fall through to Xlib fallback on X11

        # Fallback to Xlib on X11 (legacy support)
        if not self.is_wayland and self._xlib_display and HAS_XLIB:
            try:
                root = self._xlib_display.screen().root
                window_title_lower = self.window_title.lower()

                def search_windows(window):
                    """Recursively search for window with matching title."""
                    try:
                        # Get window name
                        window_name = window.get_wm_name()
                        if window_name and window_title_lower in window_name.lower():
                            # Get window geometry
                            geom = window.get_geometry()
                            # Translate coordinates to root window
                            trans = window.translate_coords(root, 0, 0)

                            return {
                                'left': trans.x,
                                'top': trans.y,
                                'width': geom.width,
                                'height': geom.height,
                            }

                        # Search children
                        children = window.query_tree().children
                        for child in children:
                            result = search_windows(child)
                            if result:
                                return result
                    except (XError, AttributeError):
                        pass

                    return None

                return search_windows(root)

            except Exception as e:
                print(f"Warning: Error finding window with Xlib: {e}")
                return None

        return None

    def capture_frame(self) -> np.ndarray:
        """
        Capture a frame from the screen.

        Returns:
            numpy array of the captured frame in BGR format
        """
        start = time.perf_counter()

        if self.is_wayland:
            # Use pyscreenshot for Wayland
            if self.mode == "window":
                # Update window region periodically (every 30 frames or if not found)
                if self._window_region is None or (hasattr(self, '_frame_count') and self._frame_count % 30 == 0):
                    self._window_region = self._find_window_region()
                    if self._window_region:
                        print(f"Found {self.window_title} window at: {self._window_region}")
                    else:
                        print(f"Warning: {self.window_title} window not found, using full screen")

                if not hasattr(self, '_frame_count'):
                    self._frame_count = 0
                self._frame_count += 1

                # Capture window region if found, otherwise full screen
                if self._window_region:
                    bbox = (
                        self._window_region['left'],
                        self._window_region['top'],
                        self._window_region['left'] + self._window_region['width'],
                        self._window_region['top'] + self._window_region['height']
                    )
                    pil_image = ImageGrab.grab(bbox=bbox)
                else:
                    pil_image = ImageGrab.grab()
            else:
                # Full screen capture
                pil_image = ImageGrab.grab()

            # Convert PIL Image to numpy array (RGB)
            frame = np.array(pil_image)
            # Convert RGB to BGR
            frame = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
        else:
            # Use mss for X11
            if self.mode == "window":
                # Update window region periodically (every 30 frames or if not found)
                if self._window_region is None or (hasattr(self, '_frame_count') and self._frame_count % 30 == 0):
                    self._window_region = self._find_window_region()
                    if self._window_region:
                        print(f"Found {self.window_title} window at: {self._window_region}")
                    else:
                        print(f"Warning: {self.window_title} window not found, using full screen")

                if not hasattr(self, '_frame_count'):
                    self._frame_count = 0
                self._frame_count += 1

                # Use window region if found, otherwise fall back to monitor
                capture_region = self._window_region if self._window_region else self.sct.monitors[self.monitor_index]
                screenshot = self.sct.grab(capture_region)
            else:
                monitor = self.sct.monitors[self.monitor_index]
                screenshot = self.sct.grab(monitor)

            # Convert to numpy array
            frame = np.array(screenshot)
            # Convert BGRA to BGR
            frame = cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR)

        # Resize to target resolution
        if frame.shape[:2][::-1] != self.target_resolution:
            frame = cv2.resize(frame, self.target_resolution, interpolation=cv2.INTER_AREA)

        self._last_capture_time = time.perf_counter() - start
        return frame

    def frame_to_png_base64(self, frame: np.ndarray) -> str:
        """
        Convert a frame to PNG format and encode as base64 data URL.

        Args:
            frame: BGR numpy array

        Returns:
            Base64-encoded PNG data URL
        """
        # Convert BGR to RGB
        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

        # Convert to PIL Image
        pil_image = Image.fromarray(rgb_frame)

        # Encode as PNG to bytes
        buffer = BytesIO()
        pil_image.save(buffer, format="PNG", optimize=True)
        png_bytes = buffer.getvalue()

        # Encode to base64
        b64_data = base64.b64encode(png_bytes).decode("utf-8")

        # Return as data URL
        return f"data:image/png;base64,{b64_data}"

    def get_last_capture_time_ms(self) -> float:
        """Get the time taken for the last capture in milliseconds."""
        return self._last_capture_time * 1000

    def close(self):
        """Release resources."""
        if self.sct is not None:
            self.sct.close()
        if self._xlib_display is not None:
            self._xlib_display.close()

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()
