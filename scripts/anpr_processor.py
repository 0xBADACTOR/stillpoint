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
import re
import json
import socket
from datetime import UTC, datetime
from pathlib import Path
from typing import Optional, Tuple, List, Tuple as TPair

# Add the project root to the sys.path so we can import core.persistence
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from core.persistence.database import Database


class GPSReader:
    """Reads GPS data from gpsd via TCP socket."""

    def __init__(self, host: str = "localhost", port: int = 2947):
        self.host = host
        self.port = port
        self.socket = None
        self.connected = False
        self.lat = None
        self.lon = None
        self._connect()

    def _connect(self) -> None:
        """Connect to gpsd."""
        try:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.settimeout(5.0)
            self.socket.connect((self.host, self.port))
            # Watch for JSON output
            self.socket.sendall(b'?WATCH={"enable":true,"json":true};\n')
            self.connected = True
        except Exception as e:
            print(f"GPS: Failed to connect to gpsd at {self.host}:{self.port}: {e}")
            self.connected = False

    def read(self) -> Optional[Tuple[float, float]]:
        """Read the latest GPS fix.

        Returns:
            Tuple of (latitude, longitude) or None if unavailable.
        """
        if not self.connected or not self.socket:
            return None

        try:
            # Receive data
            data = self.socket.recv(4096).decode('utf-8')
            # Parse JSON lines
            for line in data.strip().split('\n'):
                if not line:
                    continue
                try:
                    report = json.loads(line)
                    if report.get('class') == 'TPV':
                        lat = getattr(report, 'lat', None)
                        lon = getattr(report, 'lon', None)
                        if lat is not None and lon is not None:
                            self.lat = float(lat)
                            self.lon = float(lon)
                            return (self.lat, self.lon)
                except (json.JSONDecodeError, AttributeError, ValueError):
                    continue
            return (self.lat, self.lon) if self.lat is not None and self.lon is not None else None
        except Exception as e:
            print(f"GPS: Error reading from gpsd: {e}")
            self.connected = False
            return None

    def close(self) -> None:
        """Close the socket."""
        if self.socket:
            try:
                self.socket.sendall(b'?WATCH={"enable":false};\n')
            except:
                pass
            self.socket.close()
            self.socket = None
            self.connected = False


class ANPRProcessor:
    """Handles license plate detection and recognition."""

    def __init__(self, use_paddleocr: bool = True, gps_reader: Optional[GPSReader] = None):
        """
        Initialize the ANPR processor.

        Args:
            use_paddleocr: If True, use PaddleOCR; otherwise use Tesseract fallback
            gps_reader: Optional GPSReader instance for geotagging
        """
        self.use_paddleocr = use_paddleocr
        self.ocr = None
        self.gps_reader = gps_reader
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

        # Common OCR misrecognitions for license plates
        self.ocr_corrections = {
            'O': '0', 'o': '0',
            'I': '1', 'i': '1', 'l': '1', '|': '1',
            'S': '5', 's': '5',
            'B': '8', 'b': '6', # context dependent, but we'll try
            'G': '6', 'g': '6',
            'Z': '2', 'z': '2',
        }

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

        # Method 1: Use Haar cascade for license plates (note: this cascade is for Russian plates; may need to be replaced for other regions)
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
        Recognize text from a license plate image with multiple attempts.

        Args:
            plate_image: Cropped license plate image (grayscale)

        Returns:
            Tuple of (recognized_text, confidence) or (None, 0.0) if failed
        """
        if self.ocr is None:
            return None, 0.0

        best_text = None
        best_confidence = 0.0

        try:
            if self.use_paddleocr:
                # Try multiple preprocessing approaches for PaddleOCR
                preprocessed_images = self._get_preprocessing_variants(plate_image)
                for proc_img in preprocessed_images:
                    text, confidence = self._recognize_with_paddleocr(proc_img)
                    if text and confidence > best_confidence:
                        best_text = text
                        best_confidence = confidence
            else:
                # Tesseract fallback with multiple configs
                configs = [
                    r'--oem 3 --psm 8 -c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789',
                    r'--oem 3 --psm 7 -c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789',
                    r'--oem 3 --psm 6 -c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789',
                ]
                for config in configs:
                    text, confidence = self._recognize_with_tesseract(plate_image, config)
                    if text and confidence > best_confidence:
                        best_text = text
                        best_confidence = confidence

            # Apply OCR corrections and normalization
            if best_text:
                normalized = self.normalize_plate(best_text)
                # Recalculate confidence based on validation
                if self.validate_plate(normalized):
                    return normalized, best_confidence * 0.9  # Slight penalty for normalization
                else:
                    # If normalization fails validation, try raw with lower confidence
                    return best_text, best_confidence * 0.7

            return None, 0.0
        except Exception as e:
            print(f"OCR recognition failed: {e}")
            return None, 0.0

    def _get_preprocessing_variants(self, image: np.ndarray) -> List[np.ndarray]:
        """Generate preprocessing variants for OCR."""
        variants = []
        # Original
        variants.append(image)
        # Gaussian blur
        blurred = cv2.GaussianBlur(image, (3,3), 0)
        variants.append(blurred)
        # Adaptive threshold
        thresh = cv2.adaptiveThreshold(image, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                      cv2.THRESH_BINARY, 11, 2)
        variants.append(thresh)
        # Morphological close
        kernel = np.ones((2,2), np.uint8)
        closed = cv2.morphologyEx(image, cv2.MORPH_CLOSE, kernel)
        variants.append(closed)
        return variants

    def _recognize_with_paddleocr(self, plate_image: np.ndarray) -> Tuple[Optional[str], float]:
        """Recognize text using PaddleOCR."""
        if len(plate_image.shape) == 2:  # Grayscale
            plate_image = cv2.cvtColor(plate_image, cv2.COLOR_GRAY2BGR)

        result = self.ocr.ocr(plate_image, cls=True)
        if result and result[0]:
            text = result[0][0][1][0]  # Extract text
            confidence = result[0][0][1][1]  # Extract confidence
            return text.upper(), confidence
        return None, 0.0

    def _recognize_with_tesseract(self, plate_image: np.ndarray, config: str) -> Tuple[Optional[str], float]:
        """Recognize text using Tesseract with given config."""
        import pytesseract
        # Configure for license plates (single block of text)
        text = pytesseract.image_to_string(plate_image, config=config)
        text = ''.join(filter(str.isalnum, text)).upper()  # Keep only alphanumeric
        if text:
            # Simple confidence estimation based on length and character variety
            confidence = min(0.9, len(text) / 8.0)  # Assume 8 chars is good
            # Boost confidence if all alphanumeric and reasonable length
            if 2 <= len(text) <= 10 and text.isalnum():
                confidence = min(0.95, confidence + 0.1)
            return text, confidence
        return None, 0.0

    def normalize_plate(self, text: str) -> str:
        """
        Normalize license plate text by applying OCR corrections and formatting.

        Args:
            text: Raw recognized text

        Returns:
            Normalized text string
        """
        if not text:
            return ""

        # Convert to uppercase
        text = text.upper()

        # Remove common separators
        text = re.sub(r'[-\s_.]', '', text)

        # Apply character corrections based on common OCR errors
        corrected = []
        for char in text:
            corrected.append(self.ocr_corrections.get(char, char))
        text = ''.join(corrected)

        return text

    def validate_plate(self, text: str) -> bool:
        """
        Validate if the normalized text looks like a license plate.

        Args:
            text: Normalized text string

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

    def process_frame(self, frame: np.ndarray) -> List[Tuple[str, float, np.ndarray, Optional[float], Optional[float]]]:
        """
        Process a single frame to detect and recognize license plates.

        Args:
            frame: Input BGR frame from camera

        Returns:
            List of (plate_text, confidence, plate_image, latitude, longitude) tuples
        """
        results = []

        # Preprocess the image
        processed = self.preprocess_image(frame)

        # Detect potential license plate regions
        plate_regions = self.detect_license_plate(processed)

        # Get current GPS location if available
        lat, lon = None, None
        if self.gps_reader:
            gps_data = self.gps_reader.read()
            if gps_data:
                lat, lon = gps_data

        for plate_image, detection_confidence in plate_regions:
            # Recognize text in the plate region
            text, ocr_confidence = self.recognize_text(plate_image)

            if text and self.validate_plate(text):
                # Combined confidence: detection * OCR
                combined_confidence = detection_confidence * ocr_confidence
                results.append((text, combined_confidence, plate_image, lat, lon))

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


def process_image_file(image_path: str) -> List[Tuple[str, float, np.ndarray, Optional[float], Optional[float]]]:
    """
    Process a single image file for license plates.

    Args:
        image_path: Path to the image file

    Returns:
        List of (plate_text, confidence, plate_image, latitude, longitude) tuples
    """
    if not os.path.exists(image_path):
        print(f"Error: Image file not found: {image_path}")
        return []

    frame = cv2.imread(image_path)
    if frame is None:
        print(f"Error: Could not read image file: {image_path}")
        return []

    # For image files, we don't have GPS, so pass None
    processor = ANPRProcessor(gps_reader=None)
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
    parser.add_argument(
        "--gps-host",
        type=str,
        default="localhost",
        help="GPSD host (default: localhost)"
    )
    parser.add_argument(
        "--gps-port",
        type=int,
        default=2947,
        help="GPSD port (default: 2947)"
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
        if not args.image:
            print(f"GPS: {args.gps_host}:{args.gps_port}")

    frame_count = 0
    saved_count = 0

    # Initialize GPS reader if not processing images
    gps_reader = None
    if not args.image:
        gps_reader = GPSReader(host=args.gps_host, port=args.gps_port)

    with Database(args.db_path) as db:
        try:
            if args.image:
                # Process single image file
                results = process_image_file(args.image)
                frame_count = 1

                for plate_text, confidence, plate_image, lat, lon in results:
                    _process_detection(db, plate_text, confidence, plate_image, lat, lon,
                                     args.save_detections, saved_count)
                    saved_count += 1

                print(f"Processed {frame_count} image, found {len(results)} license plates")
            else:
                # Check if camera is available before starting live feed
                test_cap = cv2.VideoCapture(args.camera)
                if not test_cap.isOpened():
                    print(f"Error: Cannot open camera {args.camera}. Please ensure a camera is connected and the index is correct.")
                    print("If you wish to process image files, use the --image option.")
                    if gps_reader:
                        gps_reader.close()
                    return
                test_cap.release()

                # Process live camera feed
                print("Press Ctrl+C to stop...")
                processor = ANPRProcessor(gps_reader=gps_reader)
                while True:
                    frame = capture_from_camera(args.camera)
                    if frame is None:
                        print("Failed to capture frame, retrying in 1 second...")
                        time.sleep(1)
                        continue

                    frame_count += 1
                    results = processor.process_frame(frame)

                    for plate_text, confidence, plate_image, lat, lon in results:
                        _process_detection(db, plate_text, confidence, plate_image, lat, lon,
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
        finally:
            if gps_reader:
                gps_reader.close()


def _process_detection(db: Database, plate_text: str, confidence: float,
                      plate_image: np.ndarray, lat: Optional[float], lon: Optional[float],
                      save_images: bool, saved_count: int) -> None:
    """
    Process a single license plate detection and store it in the database.

    Args:
        db: Database connection
        plate_text: Recognized license plate text
        confidence: Confidence score (0.0 to 1.0)
        plate_image: Cropped plate image (numpy array)
        lat: Latitude (optional)
        lon: Longitude (optional)
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
    db.execute(
        """
        INSERT INTO detections (signal_id, seen_at, lat, lon, rssi, source, raw)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            signal_id,
            timestamp,
            lat,  # lat - from GPS correlation
            lon,  # lon - from GPS correlation
            int(confidence * 100),  # rssi field reused for confidence (0-100)
            'anpr_camera',
            f'{{"plate_text": "{plate_text}", "confidence": {confidence}, "image_saved": {save_images}}}'
        ),
    )

    print(f"Detected license plate: {plate_text} (confidence: {confidence:.2f})"
          + (f" at ({lat:.6f}, {lon:.6f})" if lat is not None and lon is not None else ""))


if __name__ == "__main__":
    main()