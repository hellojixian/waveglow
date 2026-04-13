"""
Audio loading and envelope extraction.
Adapted from seewav (public domain) by Alexandre Défossez.
"""

import json
import subprocess as sp
import numpy as np


def read_audio(audio_path, seek=None, duration=None):
    """
    Read audio file, return (float[channels, samples], samplerate).
    """
    proc = sp.run([
        'ffprobe', "-loglevel", "panic",
        str(audio_path), '-print_format', 'json', '-show_format', '-show_streams'
    ], capture_output=True)
    if proc.returncode:
        raise IOError(f"{audio_path} does not exist or is wrong type.")

    info = json.loads(proc.stdout.decode('utf-8'))
    stream = info['streams'][0]
    if stream["codec_type"] != "audio":
        raise ValueError(f"{audio_path} should contain only audio.")

    samplerate = float(stream['sample_rate'])

    command = ['ffmpeg', '-y', '-loglevel', 'panic']
    if seek is not None:
        command += ['-ss', str(seek)]
    command += ['-i', str(audio_path)]
    if duration is not None:
        command += ['-t', str(duration)]
    command += ['-f', 'f32le', '-ac', '1', '-']

    proc = sp.run(command, check=True, capture_output=True)
    wav = np.frombuffer(proc.stdout, dtype=np.float32)
    return wav, samplerate


def sigmoid(x):
    return 1 / (1 + np.exp(-x))


def get_envelope(wav, sr, time=0.4, bars=80, oversample=4):
    """
    Extract amplitude envelope. Returns float[n_frames] normalized to [0, 1].
    (Based on seewav's envelope extraction with sigmoid compression.)
    """
    window = int(sr * time / bars)
    stride = int(window / oversample)

    wav = np.pad(wav, window // 2)
    out = []
    for off in range(0, len(wav) - window, stride):
        frame = wav[off:off + window]
        out.append(np.maximum(frame, 0).mean())
    out = np.array(out)
    # sigmoid compression (from seewav)
    out = 1.9 * (sigmoid(2.5 * out) - 0.5)
    return out


def get_rms_per_frame(wav, sr, fps=30):
    """
    Get RMS amplitude per video frame. Returns float[n_frames] in [0, 1].
    """
    samples_per_frame = int(sr) // fps
    frames = []
    for i in range(len(wav) // samples_per_frame):
        chunk = wav[i * samples_per_frame:(i + 1) * samples_per_frame]
        rms = np.sqrt(np.mean(chunk ** 2))
        frames.append(rms)
    arr = np.array(frames)
    if arr.max() > 0:
        arr = arr / arr.max()
    return arr


def get_fft_per_frame(wav, sr, fps=30, n_bins=80):
    """
    Get FFT magnitude per video frame, log-scaled to n_bins.
    Returns float[n_frames, n_bins] in [0, 1].
    """
    samples_per_frame = int(sr) // fps
    fft_size = 2048
    results = []

    log_indices = np.logspace(0, np.log10(fft_size // 2 - 1), n_bins).astype(int)
    log_indices = np.clip(log_indices, 0, fft_size // 2 - 1)

    for i in range(len(wav) // samples_per_frame):
        chunk = wav[i * samples_per_frame:i * samples_per_frame + fft_size]
        if len(chunk) < fft_size:
            chunk = np.pad(chunk, (0, fft_size - len(chunk)))
        fft = np.abs(np.fft.rfft(chunk * np.hanning(fft_size)))[:fft_size // 2]
        bins = fft[log_indices]
        results.append(bins)

    arr = np.array(results, dtype=np.float32)
    max_val = arr.max()
    if max_val > 0:
        arr /= max_val
    return arr
