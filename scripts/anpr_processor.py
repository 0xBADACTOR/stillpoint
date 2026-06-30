#!/usr/bin/env python3
"""Automatic Number Plate Recognition (ANPR) processor for StillPoint.

Captures images from a camera, detects license plates using OCR,
and writes normalized detections into the persistence layer.
"""
from __future__ import annotations

import cv2
import numpy as np
import time
import os
import sys
import re  # Added missing import
from datetime import UTC, datetime
from pathlib import Path
from typing import Optional, Tuple, List

# Add the project root to the sys.path so we can import core.persistence
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from core.persistence.database import Database


class ANPRProcessor:
    """Handles license plate detection and recognition."""

    def __init__(self, use_paddleocr: bool = True):
        """
        Initialize the ANPR processor.

        Args:
            use_paddleocr: If True, use PaddleOCR; otherwise use Tesseract fallback
        """
        self.use_paddleocr = use_paddleocr
        self.ocr = None
        self._initialize_ocr()

        # Common license plate patterns for validation (US-centric, can be extended)
        self.plate_patterns = [
            r'^[A-Z]{3}[0-9]{3}$',           # ABC123
            r'^[A-Z]{2}[0-9]{4}$',           # AB1234
            r'^[A-Z][0-9]{3}[A-Z]{2}$',      # A123AB
            r'^[0-9]{3}[A-Z]{3}$',           # 123ABC
            r'^[A-Z]{1}[0-9]{3}[A-Z]{1}[0-9]{1}$', # A123B4
            r'^[A-Z]{2}[0-9]{2}[A-Z]{2}$',   # AB12CD
        ]

    def _initialize_ocr(self) -> None:
        """Initialize the OCR engine."""
        if self.use_paddleocr:
            try:
                from paddleocr import PaddleOCR
                # Use English model, enable license plate optimization if available
                self.ocr = PaddleOCR(use_angle_cls=True, lang='en', show_log=False)
                print("PaddleOCR initialized successfully")
            except ImportError:
                print("PaddleOCR not available, falling back to Tesseract")
                self.use_paddleocr = False
                self._initialize_tesseract()
        else:
            self._initialize_tesseract()

    def _initialize_tesseract(self) -> None:
        """Initialize Tesseract OCR as fallback."""
        try:
            import pytesseract
            # Check if tesseract is available
            pytesseract.get_tesseract_version()
            print("Tesseract OCR initialized successfully")
        except ImportError:
            print("Warning: Neither PaddleOCR nor Tesseract available. ANPR will not work.")
            self.ocr = None
        except Exception as e:
            print(f"Tesseract not properly installed: {e}")
            self.ocr = None

    def preprocess_image(self, image: np.ndarray) -> np.ndarray:
        """
        Preprocess image for better license plate detection.

        Args:
            image: Input BGR image

        Returns:
            Preprocessed grayscale image
        """
        # Convert to grayscale
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

        # Apply bilateral filter to reduce noise while keeping edges sharp
        gray = cv2.bilateralFilter(gray, 11, 17, 17)

        # Apply adaptive histogram equalization for better contrast
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8,8))
        gray = clahe.apply(gray)

        return gray

    def detect_license_plate(self, image: np.ndarray) -> List[Tuple[np.ndarray, float]]:
        """
        Detect license plate regions in the image.
        This is a simplified implementation - in practice, you'd use a trained
        model like Haar cascades, YOLO, or EAST text detector.

        Args:
            image: Preprocessed grayscale image

        Returns:
            List of (cropped_plate_image, confidence) tuples
        """
        detections = []

        # Method 1: Use Haar cascade for license plates (if available)
        try:
            plate_cascade = cv2.CascadeClassifier(
                cv2.data.haarcascades + 'haarcascade_russian_plate_number.xml'
            )
            if not plate_cascade.empty():
                plates = plate_cascade.detectMultiScale(
                    image,
                    scaleFactor=1.1,
                    minNeighbors=5,
                    minSize=(30, 30),
                    flags=cv2.CASCADE_SCALE_IMAGE
                )

                for (x, y, w, h) in plates:
                    # Add some padding
                    padding = int(0.1 * w)
                    x1 = max(0, x - padding)
                    y1 = max(0, y - padding)
                    x2 = min(image.shape[1], x + w + padding)
                    y2 = min(image.shape[0], y + h + padding)

                    plate_roi = image[y1:y2, x1:x2]
                    detections.append((plate_roi, 0.8))  # Fixed confidence for Haar
        except Exception as e:
            print(f"Haar cascade detection failed: {e}")

        # Method 2: Contour-based detection (fallback)
        if not detections:
            detections.extend(self._detect_plates_by_contours(image))

        return detections

    def _detect_plates_by_contours(self, image: np.ndarray) -> List[Tuple[np.ndarray, float]]:
        """
        Detect license plates using contour analysis.

        Args:
            image: Preprocessed grayscale image

        Returns:
            List of (cropped_plate_image, confidence) tuples
        """
        detections = []

        # Apply edge detection
        edged = cv2.Canny(image, 30, 200)

        # Find contours
        contours, _ = cv2.findContours(
            edged.copy(), cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE
        )

        # Sort contours by area (largest first)
        contours = sorted(contours, key=cv2.contourArea, reverse=True)[:10]

        for contour in contours:
            # Approximate the contour
            peri = cv2.arcLength(contour, True)
            approx = cv2.approxPolyDP(contour, 0.02 * peri, True)

            # License plates are typically rectangular
            if len(approx) == 4:
                x, y, w, h = cv2.boundingRect(approx)
                aspect_ratio = w / float(h)

                # License plates usually have aspect ratio between 2:1 and 5:1
                if 2.0 <= aspect_ratio <= 5.0:
                    # Extract the region of interest
                    roi = image[y:y+h, x:x+w]
                    detections.append((roi, 0.6))  # Lower confidence for contour method

        return detections

    def recognize_text(self, plate_image: np.ndarray) -> Tuple[Optional[str], float]:
        """
        Recognize text from a license plate image.

        Args:
            plate_image: Cropped license plate image (grayscale)

        Returns:
            Tuple of (recognized_text, confidence) or (None, 0.0) if failed
        """
        if self.ocr is None:
            return None, 0.0

        try:
            if self.use_paddleocr:
                # PaddleOCR expects BGR or RGB image
                if len(plate_image.shape) == 2:  # Grayscale
                    plate_image = cv2.cvtColor(plate_image, cv2.COLOR_GRAY2BGR)

                result = self.ocr.ocr(plate_image, cls=True)
                if result and result[0]:
                    text = result[0][0][1][0]  # Extract text
                    confidence = result[0][0][1][1]  # Extract confidence
                    return text.upper(), confidence
            else:
                # Tesseract fallback
                import pytesseract
                # Configure for license plates (single block of text)
                custom_config = r'--oem 3 --psm 8 -c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789'
                text = pytesseract.image_to_string(plate_image, config=custom_config)
                text = ''.join(filter(str.isalnum, text)).upper()  # Keep only alphanumeric
                if text:
                    # Simple confidence estimation based on length and character variety
                    confidence = min(0.9, len(text) / 8.0)  # Assume 8 chars is good
                    return text, confidence

            return None, 0.0
        except Exception as e:
            print(f"OCR recognition failed: {e}")
            return None, 0.0

    def validate_plate(self, text: str) -> bool:
        """
        Validate if the recognized text looks like a license plate.

        Args:
            text: Recognized text string

        Returns:
            True if text matches common license plate patterns
        """
        if not text or len(text) < 2 or len(text) > 10:
            return False

        # Check against known patterns
        for pattern in self.plate_patterns:
            if re.match(pattern, text):
                return True

        # Additional heuristics: should contain both letters and numbers
        has_letter = any(c.isalpha() for c in text)
        has_number = any(c.isdigit() for c in text)

        return has_letter and has_number and 2 <= len(text) <= 10

    def process_frame(self, frame: np.ndarray) -> List[Tuple[str, float, np.ndarray]]:
        """
        Process a single frame to detect and recognize license plates.

        Args:
            frame: Input BGR frame from camera

        Returns:
            List of (plate_text, confidence, plate_image) tuples
        """
        results = []

        # Preprocess the image
        processed = self.preprocess_image(frame)

        # Detect potential license plate regions
        plate_regions = self.detect_license_plate(processed)

        for plate_image, detection_confidence in plate_regions:
            # Recognize text in the plate region
            text, ocr_confidence = self.recognize_text(plate_image)

            if text and self.validate_plate(text):
                # Combined confidence: detection * OCR
                combined_confidence = detection_confidence * ocr_confidence
                results.append((text, combined_confidence, plate_image))

        return results


def capture_from_camera(camera_index: int = 0) -> Optional[np.ndarray]:
    """
    Capture a single frame from a camera.

    Args:
        camera_index: Index of the camera to use (0 for default)

    Returns:
        Captured frame as numpy array, or None if failed
    """
    cap = cv2.VideoCapture(camera_index)
    if not cap.isOpened():
        print(f"Error: Could not open camera {camera_index}")
        return None

    # Set camera properties for better plate capture
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
    cap.set(cv2.CAP_PROP_FPS, 30)

    ret, frame = cap.read()
    cap.release()

    if not ret:
        print("Error: Could not read frame from camera")
        return None

    return frame


def process_image_file(image_path: str) -> List[Tuple[str, float, np.ndarray]]:
    """
    Process a single image file for license plates.

    Args:
        image_path: Path to the image file

    Returns:
        List of (plate_text, confidence, plate_image) tuples
    """
    if not os.path.exists(image_path):
        print(f"Error: Image file not found: {image_path}")
        return []

    frame = cv2.imread(image_path)
    if frame is None:
        print(f"Error: Could not read image file: {image_path}")
        return []

    processor = ANPRProcessor()
    return processor.process_frame(frame)


def main() -> None:
    """Main function for ANPR processing."""
    import argparse  # Moved inside function to avoid circular import issues

    parser = argparse.ArgumentParser(
        description="Process images for license plate recognition and store in StillPoint database."
    )
    parser.add_argument(
        "--camera",
        type=int,
        default=0,
        help="Camera index to use (default: 0)"
    )
    parser.add_argument(
        "--image",
        type=str,
        help="Path to a single image file to process (instead of live camera)"
    )
    parser.add_argument(
        "--db",
        dest="db_path",
        default=os.path.join(PROJECT_ROOT, "data", "stillpoint.db"),
        help="Path to the SQLite database file (default: ./data/stillpoint.db)"
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=1.0,
        help="Interval between captures in seconds when using live camera (default: 1.0)"
    )
    parser.add_argument(
        "--save-detections",
        action="store_true",
        help="Save detected plate images to ./detected_plates/ directory"
    )
    args = parser.parse_args()

    # Create detections directory if saving images
    if args.save_detections:
        os.makedirs("./detected_plates", exist_ok=True)

    # Initialize database connection
    os.makedirs(os.path.dirname(args.db_path), exist_ok=True)

    print("Starting ANPR processor...")
    print(f"Database: {args.db_path}")
    if args.image:
        print(f"Processing image: {args.image}")
    else:
        print(f"Using camera {args.camera} with {args.interval}s interval")

    frame_count = 0
    saved_count = 0

    with Database(args.db_path) as db:
        try:
            if args.image:
                # Process single image file
                results = process_image_file(args.image)
                frame_count = 1

                for plate_text, confidence, plate_image in results:
                    _process_detection(db, plate_text, confidence, plate_image,
                                     args.save_detections, saved_count)
                    saved_count += 1

                print(f"Processed {frame_count} image, found {len(results)} license plates")
            else:
                # Check if camera is available before starting live feed
                test_cap = cv2.VideoCapture(args.camera)
                if not test_cap.isOpened():
                    print(f"Error: Cannot open camera {args.camera}. Please ensure a camera is connected and the index is correct.")
                    print("If you wish to process image files, use the --image option.")
                    return
                test_cap.release()

                # Process live camera feed
                print("Press Ctrl+C to stop...")
                while True:
                    frame = capture_from_camera(args.camera)
                    if frame is None:
                        print("Failed to capture frame, retrying in 1 second...")
                        time.sleep(1)
                        continue

                    frame_count += 1
                    processor = ANPRProcessor()
                    results = processor.process_frame(frame)

                    for plate_text, confidence, plate_image in results:
                        _process_detection(db, plate_text, confidence, plate_image,
                                         args.save_detections, saved_count)
                        saved_count += 1

                    if frame_count % 30 == 0:  # Status update every 30 frames
                        print(f"Processed {frame_count} frames, saved {saved_count} detections")

                    time.sleep(args.interval)

        except KeyboardInterrupt:
            print(f"\nStopped. Processed {frame_count} frames, saved {saved_count} detections.")
        except Exception as e:
            print(f"Error in main loop: {e}")
            raise


def _process_detection(db: Database, plate_text: str, confidence: float,
                      plate_image: np.ndarray, save_images: bool, saved_count: int) -> None:
    """
    Process a single license plate detection and store it in the database.

    Args:
        db: Database connection
        plate_text: Recognized license plate text
        confidence: Confidence score (0.0 to 1.0)
        plate_image: Cropped plate image (numpy array)
        save_images: Whether to save the plate image to disk
        saved_count: Current count of saved detections (for filename)
    """
    # Hash the license plate for privacy (unless plain plates enabled)
    plain_plates_enabled = db.plain_plates_enabled()
    identifier_plain = plate_text if plain_plates_enabled else None

    try:
        identifier_hash = db.hash_identifier(plate_text)
    except RuntimeError:
        print("Database not bootstrapped. Call bootstrap() first.")
        return

    # Get current timestamp
    timestamp = datetime.now(UTC).isoformat(timespec="seconds")

    # Insert or update the signal (license plate)
    # We treat license plates as signals with signal_type='anpr'
    cursor = db.execute(
        """
        INSERT INTO signals (signal_type, identifier_hash, identifier_plain, first_seen, last_seen)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(identifier_hash) DO UPDATE SET
            last_seen = excluded.last_seen
        """,
        (
            'anpr',  # signal_type for license plates
            identifier_hash,
            identifier_plain,
            timestamp,
            timestamp,
        ),
    )

    # Get the signal_id
    signal_id = db.fetchone(
        "SELECT id FROM signals WHERE identifier_hash = ?",
        (identifier_hash,),
    )["id"]

    # Save plate image if requested
    if save_images and plate_image is not None:
        image_path = f"./detected_plates/plate_{saved_count:06d}_{plate_text}_{int(time.time())}.jpg"
        cv2.imwrite(image_path, plate_image)
        # Optionally, we could store the image path in the database
        # but for simplicity, we'll just save the raw detection data

    # Insert the detection record
    # For ANPR, we don't have GPS coordinates from the camera itself
    # In a real implementation, we'd get GPS from a separate GPS module
    # For now, we'll leave lat/lon as NULL and rely on external GPS tagging
    # This assumes that the ANPR system is synchronized with a GPS source
    # that provides location data separately (to be correlated by timestamp)
    db.execute(
        """
        INSERT INTO detections (signal_id, seen_at, lat, lon, rssi, source, raw)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            signal_id,
            timestamp,
            None,  # lat - to be filled by GPS correlation
            None,  # lon - to be filled by GPS correlation
            int(confidence * 100),  # rssi field reused for confidence (0-100)
            'anpr_camera',
            f'{{"plate_text": "{plate_text}", "confidence": {confidence}, "image_saved": {save_images}}}'
        ),
    )

    print(f"Detected license plate: {plate_text} (confidence: {confidence:.2f})")


if __name__ == "__main__":
    main()