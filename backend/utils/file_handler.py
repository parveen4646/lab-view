import os
import logging

logger = logging.getLogger(__name__)


class FileHandler:
    def __init__(self, upload_folder: str = "uploads"):
        self.upload_folder = upload_folder
        self._allowed = {"pdf"}
        os.makedirs(upload_folder, exist_ok=True)

    def is_allowed_file(self, filename: str) -> bool:
        return "." in filename and filename.rsplit(".", 1)[1].lower() in self._allowed
