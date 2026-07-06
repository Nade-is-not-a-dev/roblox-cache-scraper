"""Audio player widget using sounddevice."""

import threading
import time
import tempfile
from pathlib import Path

import numpy as np
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import (
    QHBoxLayout, QLabel, QPushButton, QSlider, QVBoxLayout, QWidget,
)

try:
    import sounddevice as sd
    import soundfile as sf
    HAS_AUDIO = True
except ImportError:
    HAS_AUDIO = False


class AudioPlayerWidget(QWidget):
    """Audio player with play/pause, volume, and seek controls."""

    def __init__(self, data: bytes, parent=None):
        super().__init__(parent)
        self.data = data
        self.is_playing = False
        self.is_scrubbing = False
        self.should_stop = False
        self.playback_position = 0
        self.audio_data = None
        self.sample_rate = None
        self.duration = 0.0
        self.volume = 0.7
        self.stream = None
        self.stop_event = None
        self.position_lock = threading.Lock()

        self._load_audio()
        self._setup_ui()

        self.timer = QTimer()
        self.timer.timeout.connect(self._update_ui)
        self.timer.start(50)

    def _load_audio(self):
        """Load audio from bytes."""
        if not HAS_AUDIO or not self.data:
            self.duration = 0
            return

        try:
            # Write to temp file for soundfile to read
            with tempfile.NamedTemporaryFile(suffix='.ogg', delete=False) as f:
                f.write(self.data)
                tmp_path = f.name

            self.audio_data, self.sample_rate = sf.read(tmp_path, dtype='float32')
            Path(tmp_path).unlink(missing_ok=True)

            # Convert to stereo
            if len(self.audio_data.shape) == 1:
                self.audio_data = np.column_stack((self.audio_data, self.audio_data))
            elif self.audio_data.shape[1] == 1:
                self.audio_data = np.repeat(self.audio_data, 2, axis=1)
            elif self.audio_data.shape[1] > 2:
                mono = self.audio_data.mean(axis=1)
                self.audio_data = np.column_stack((mono, mono))

            self.audio_data = np.ascontiguousarray(np.clip(self.audio_data, -1.0, 1.0), dtype=np.float32)
            self.duration = len(self.audio_data) / self.sample_rate if self.sample_rate else 0
        except Exception as e:
            print(f'Audio load error: {e}')
            self.duration = 0

    def _setup_ui(self):
        layout = QVBoxLayout()
        layout.setContentsMargins(10, 10, 10, 10)
        layout.addStretch()

        controls = QVBoxLayout()
        controls.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # Progress
        self.progress_slider = QSlider(Qt.Orientation.Horizontal)
        self.progress_slider.setRange(0, max(1, int(self.duration * 1000)))
        self.progress_slider.sliderPressed.connect(lambda: setattr(self, 'is_scrubbing', True))
        self.progress_slider.sliderReleased.connect(self._end_scrub)
        controls.addWidget(self.progress_slider)

        # Buttons
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        self.play_btn = QPushButton('▶ Play')
        self.play_btn.clicked.connect(self._toggle)
        btn_row.addWidget(self.play_btn)
        self.time_label = QLabel('00:00 / 00:00')
        btn_row.addWidget(self.time_label)
        btn_row.addStretch()
        controls.addLayout(btn_row)

        layout.addLayout(controls)
        layout.addStretch()
        self.setLayout(layout)

    def _toggle(self):
        if not HAS_AUDIO or self.audio_data is None:
            return
        if self.is_playing:
            self._pause()
        else:
            self._play()

    def _play(self):
        with self.position_lock:
            if self.playback_position >= len(self.audio_data):
                self.playback_position = 0

        self.is_playing = True
        self.should_stop = False
        self.play_btn.setText('⏸ Pause')
        self.stop_event = threading.Event()

        t = threading.Thread(target=self._playback_worker, args=(self.stop_event,), daemon=True)
        t.start()

    def _pause(self):
        self.is_playing = False
        self.should_stop = True
        self.play_btn.setText('▶ Play')
        if self.stop_event:
            self.stop_event.set()

    def _end_scrub(self):
        new_time = self.progress_slider.value() / 1000.0
        new_time = max(0, min(new_time, self.duration))
        with self.position_lock:
            self.playback_position = int(new_time * self.sample_rate) if self.sample_rate else 0
        self.is_scrubbing = False

    def _playback_worker(self, stop_event):
        def callback(outdata, frames, time_info, status):
            with self.position_lock:
                start = self.playback_position
                end = min(start + frames, len(self.audio_data))
                size = end - start
                if size <= 0 or stop_event.is_set():
                    outdata[:] = 0
                    stop_event.set()
                    return
                chunk = self.audio_data[start:end] * self.volume
                outdata[:size] = chunk
                if size < frames:
                    outdata[size:] = 0
                self.playback_position = end

        try:
            stream = sd.OutputStream(
                samplerate=self.sample_rate, channels=2,
                dtype='float32', callback=callback, blocksize=2048,
            )
            stream.start()
            while not stop_event.is_set():
                time.sleep(0.01)
                with self.position_lock:
                    if self.playback_position >= len(self.audio_data):
                        self.should_stop = True
                        stop_event.set()
            stream.stop()
            stream.close()
        except Exception as e:
            print(f'Audio playback error: {e}')
        self.is_playing = False

    def _update_ui(self):
        if not self.is_scrubbing and self.sample_rate:
            with self.position_lock:
                t = self.playback_position / self.sample_rate
            self.progress_slider.setValue(int(t * 1000))
            self.time_label.setText(f'{self._fmt(t)} / {self._fmt(self.duration)}')

    def _fmt(self, s):
        m = int(s // 60)
        sec = int(s % 60)
        return f'{m:02d}:{sec:02d}'

    def stop(self):
        self.should_stop = True
        self.is_playing = False
        if self.stop_event:
            self.stop_event.set()
        if self.timer:
            self.timer.stop()
