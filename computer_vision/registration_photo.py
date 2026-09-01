"""OpenCV utilities used only for candidate registration photographs."""

from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import cv2


class PhotoCaptureError(Exception):
    status_code = 503


def save_registration_frame(frame, storage_dir):
    """Validate and persist one OpenCV frame, returning its safe relative reference."""
    if frame is None or getattr(frame, "size", 0) == 0:
        raise PhotoCaptureError("no image frame was captured")
    directory = Path(storage_dir)
    directory.mkdir(parents=True, exist_ok=True)
    filename = f"registration_{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}_{uuid4().hex}.jpg"
    destination = directory / filename
    if not cv2.imwrite(str(destination), frame):
        raise PhotoCaptureError("could not save the registration photo")
    return str(destination)


def validate_registration_photo_path(photo_path, storage_dir):
    """Accept only an existing registration image located in the configured store."""
    if not photo_path:
        return None
    root = Path(storage_dir).resolve()
    candidate = Path(photo_path).resolve()
    try:
        candidate.relative_to(root)
    except ValueError as error:
        raise PhotoCaptureError("registration photo path is outside the configured storage directory") from error
    if candidate.suffix.lower() not in {".jpg", ".jpeg", ".png"} or not candidate.is_file():
        raise PhotoCaptureError("registration photo is not a valid saved image")
    return str(candidate)


def capture_registration_photo(storage_dir, camera_index=0):
    """Capture one frame from a webcam and always release the camera device."""
    camera = cv2.VideoCapture(camera_index)
    if not camera.isOpened():
        camera.release()
        raise PhotoCaptureError("webcam is unavailable")
    try:
        success, frame = camera.read()
        if not success:
            raise PhotoCaptureError("webcam did not return an image")
        return save_registration_frame(frame, storage_dir)
    finally:
        camera.release()
