"""Face Detector Module using OpenCV Haar Cascade."""

from pathlib import Path
from typing import List, Optional, Tuple

import cv2
import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CASCADE_PATH = PROJECT_ROOT / "computer_vision" / "haarcascade" / "haarcascade_frontalface_default.xml"


class FaceDetectorError(Exception):
    """Base exception for face detection errors."""
    pass


class FaceDetector:
    """Detects human faces in frames using OpenCV Haar Cascade."""

    def __init__(self, cascade_path: Optional[str] = None):
        self.cascade_path = Path(cascade_path) if cascade_path else DEFAULT_CASCADE_PATH
        if not self.cascade_path.is_absolute():
            self.cascade_path = (PROJECT_ROOT / self.cascade_path).resolve()

        if not self.cascade_path.exists():
            raise FaceDetectorError(f"Haar Cascade XML not found at {self.cascade_path}")

        self.classifier = cv2.CascadeClassifier(str(self.cascade_path))
        if self.classifier.empty():
            raise FaceDetectorError(f"Failed to load Haar Cascade model from {self.cascade_path}")

    def detect_faces(
        self,
        frame: np.ndarray,
        scale_factor: float = 1.1,
        min_neighbors: int = 5,
        min_size: Tuple[int, int] = (30, 30),
    ) -> List[Tuple[int, int, int, int]]:
        """Detect faces in a given frame using Haar Cascade.

        Returns a list of bounding boxes: [(x, y, width, height), ...].
        Raises ValueError on invalid frame.
        """
        if frame is None or not hasattr(frame, "shape") or getattr(frame, "size", 0) == 0:
            raise ValueError("Invalid frame: frame is None or empty")

        if len(frame.shape) < 2:
            raise ValueError("Invalid frame: invalid frame dimensions")

        # Convert to grayscale
        if len(frame.shape) == 3 and frame.shape[2] >= 3:
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        elif len(frame.shape) == 2:
            gray = frame
        else:
            gray = frame[:, :, 0]

        faces = self.classifier.detectMultiScale(
            gray,
            scaleFactor=scale_factor,
            minNeighbors=min_neighbors,
            minSize=min_size,
        )
        if faces is None or len(faces) == 0:
            return []
        return [(int(x), int(y), int(w), int(h)) for (x, y, w, h) in faces]

    def count_faces(self, frame: np.ndarray) -> int:
        """Return the number of detected faces in the frame."""
        return len(self.detect_faces(frame))

    def is_face_present(self, frame: np.ndarray) -> bool:
        """Return True if at least one face is detected in the frame."""
        return self.count_faces(frame) > 0


