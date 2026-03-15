"""Camera access and barcode decoding via pyzbar.

BarcodeService is intentionally kept thin:
- It accepts raw image data (bytes or PIL Image) and returns a decoded string.
- Camera lifecycle is managed by the Kivy widget layer (camera in tracker.kv).
- This keeps the service unit-testable without a physical device.

On iOS (kivy-ios build), pyzbar delegates to the system AVFoundation barcode
scanner via the compiled extension. Set config.ENABLE_BARCODE_SCAN = False to
disable the scan button entirely (e.g. on simulator builds).
"""

from __future__ import annotations

import logging
from typing import Callable, Optional

import config

logger = logging.getLogger(__name__)


class BarcodeService:
    """Decodes barcodes from camera frames and dispatches results via callback.

    Usage pattern in a Kivy screen:
        svc = BarcodeService(on_result=self._on_barcode)
        svc.start_scan(camera_widget)
        # ...user points camera at barcode...
        # on_result called with barcode string
        svc.stop_scan()
    """

    def __init__(self, on_result: Callable[[str], None]) -> None:
        """Initialise the service with a result handler.

        Args:
            on_result: Callable invoked with the decoded barcode string.
                Called on the Kivy main thread via Clock.schedule_once.
        """
        self._on_result = on_result
        self._scanning = False
        self._camera_widget: Optional[object] = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start_scan(self, camera_widget: object) -> bool:
        """Attach to a Kivy Camera widget and begin frame processing.

        Args:
            camera_widget: A kivy.uix.camera.Camera instance.

        Returns:
            True if scanning started successfully, False if disabled or
            pyzbar is not available.
        """
        if not config.ENABLE_BARCODE_SCAN:
            logger.info("Barcode scanning disabled by feature flag")
            return False

        if not self._pyzbar_available():
            logger.warning("pyzbar not installed; barcode scanning unavailable")
            return False

        self._camera_widget = camera_widget
        self._scanning = True
        self._bind_camera()
        logger.debug("Barcode scan started")
        return True

    def stop_scan(self) -> None:
        """Detach from the camera widget and stop processing frames."""
        self._scanning = False
        self._unbind_camera()
        self._camera_widget = None
        logger.debug("Barcode scan stopped")

    # ------------------------------------------------------------------
    # Frame processing
    # ------------------------------------------------------------------

    def process_frame(self, frame_data: bytes, width: int, height: int) -> Optional[str]:
        """Attempt to decode a barcode from a raw RGB frame.

        Designed to be called from the Kivy Camera on_texture event; keep
        processing lightweight — pyzbar exits early if no barcode is found.

        Args:
            frame_data: Raw pixel bytes in RGB format.
            width: Frame width in pixels.
            height: Frame height in pixels.

        Returns:
            Decoded barcode string if found, else None.
        """
        try:
            from pyzbar import pyzbar  # pylint: disable=import-outside-toplevel
            from PIL import Image      # pylint: disable=import-outside-toplevel

            image = Image.frombytes("RGB", (width, height), frame_data)
            decoded_objects = pyzbar.decode(image)
            for obj in decoded_objects:
                if obj.type in ("EAN13", "EAN8", "UPCA", "UPCE", "CODE128", "CODE39"):
                    return obj.data.decode("utf-8")
        except Exception as exc:  # pylint: disable=broad-except
            logger.debug("Frame decode error: %s", exc)
        return None

    def decode_image(self, image_path: str) -> Optional[str]:
        """Decode a barcode from a saved image file (useful for testing).

        Args:
            image_path: Absolute path to an image file.

        Returns:
            Decoded barcode string, or None if not found.
        """
        try:
            from pyzbar import pyzbar  # pylint: disable=import-outside-toplevel
            from PIL import Image      # pylint: disable=import-outside-toplevel

            image = Image.open(image_path)
            decoded_objects = pyzbar.decode(image)
            if decoded_objects:
                return decoded_objects[0].data.decode("utf-8")
        except Exception as exc:  # pylint: disable=broad-except
            logger.warning("decode_image failed for '%s': %s", image_path, exc)
        return None

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _bind_camera(self) -> None:
        """Bind the on_texture event to the frame processor."""
        if self._camera_widget is None:
            return
        try:
            self._camera_widget.bind(on_texture=self._on_texture)
        except AttributeError:
            pass

    def _unbind_camera(self) -> None:
        """Unbind the on_texture event."""
        if self._camera_widget is None:
            return
        try:
            self._camera_widget.unbind(on_texture=self._on_texture)
        except AttributeError:
            pass

    def _on_texture(self, camera: object, *args: object) -> None:  # noqa: ARG002
        """Kivy Camera on_texture callback — decode the latest frame.

        Args:
            camera: The Kivy Camera widget.
            *args: Additional Kivy event arguments (unused).
        """
        if not self._scanning:
            return
        try:
            texture = getattr(camera, "texture", None)
            if texture is None:
                return
            frame_bytes = texture.pixels
            w, h = texture.size
            barcode = self.process_frame(frame_bytes, w, h)
            if barcode:
                self.stop_scan()
                from kivy.clock import Clock  # pylint: disable=import-outside-toplevel
                Clock.schedule_once(lambda dt: self._on_result(barcode), 0)
        except Exception as exc:  # pylint: disable=broad-except
            logger.debug("_on_texture error: %s", exc)

    @staticmethod
    def _pyzbar_available() -> bool:
        """Return True if pyzbar can be imported.

        Returns:
            Boolean indicating library availability.
        """
        try:
            import pyzbar  # noqa: F401  pylint: disable=import-outside-toplevel
            return True
        except ImportError:
            return False
