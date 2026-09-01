import numpy as np

from computer_vision.registration_photo import save_registration_frame


def test_save_registration_frame(tmp_path):
    path = save_registration_frame(np.zeros((10, 10, 3), dtype=np.uint8), tmp_path)
    assert path.endswith(".jpg")
    assert (tmp_path / path.split("\\")[-1]).exists() or (tmp_path / path.split("/")[-1]).exists()
