import os
import sys
import io
import numpy as np
import librosa
from midiutil import MIDIFile

def separate_guitar(audio_path):
    import subprocess
    import tempfile
    
    print("[INFO] DEMUCS: Separating Guitar Track... (This may take a minute)")
    out_dir = os.path.join(os.path.dirname(__file__), "demucs_out")
    os.makedirs(out_dir, exist_ok=True)
    
    # Run Demucs using subprocess
    cmd = [
        sys.executable, "-m", "demucs.separate",
        "-n", "htdemucs", # Using the default htdemucs model (CPU friendly enough, very good)
        "--two-stems", "vocals", # Quickest trick to get non-vocals, but for just guitar we use full split
        "-d", "cpu" if not is_cuda_available() else "cuda",
        "-o", out_dir,
        audio_path
    ]
    # Actually, let's just run default 4-stem to get 'other' which contains guitar & synths
    cmd = [
        sys.executable, "-m", "demucs.separate",
        "-n", "htdemucs",
        "-d", "cpu" if not is_cuda_available() else "cuda",
        "-o", out_dir,
        audio_path
    ]
    
    subprocess.run(cmd, check=True)
    
    base_name = os.path.splitext(os.path.basename(audio_path))[0]
    # htdemucs outputs: vocals.wav, drums.wav, bass.wav, other.wav.
    # 'other.wav' is usually where the main guitars are. 
    other_track = os.path.join(out_dir, "htdemucs", base_name, "other.wav")
    
    if os.path.exists(other_track):
        return other_track
    return audio_path

def is_cuda_available():
    import torch
    return torch.cuda.is_available()

def download_btc_if_needed():
    btc_path = os.path.join(os.path.dirname(__file__), "BTC")
    if not os.path.exists(os.path.join(btc_path, "btc_model.py")):
        import subprocess
        print("[INFO] Downloading Modern Transformer AI (BTC) ...")
        subprocess.run(["git", "clone", "https://github.com/jayg996/BTC-ISMIR19.git", btc_path], check=True)
    return btc_path

def get_beat_times(audio_path):
    print("[1/4] Librosa: Analyzing Beats (Beat Sync + Onset Refinement)...")
    y, sr = librosa.load(audio_path, sr=22050)
    duration = librosa.get_duration(y=y, sr=sr)

    # Beat tracking with onset envelope for better accuracy
    onset_env = librosa.onset.onset_strength(y=y, sr=sr)
    tempo, beat_frames = librosa.beat.beat_track(y=y, sr=sr, onset_envelope=onset_env)
    beat_times = librosa.frames_to_time(beat_frames, sr=sr)

    # Onset detection for sub-beat chord change refinement
    onset_frames = librosa.onset.onset_detect(y=y, sr=sr, onset_envelope=onset_env,
                                               backtrack=True)
    onset_times = librosa.frames_to_time(onset_frames, sr=sr)

    # Merge beats + strong onsets (onsets that are far enough from any beat)
    MIN_GAP = 0.12  # minimum interval to keep (avoids micro-splits)
    combined = np.sort(np.unique(np.concatenate([[0.0], beat_times, onset_times,
                                                  [duration]])))
    # Deduplicate close times
    filtered = [combined[0]]
    for t in combined[1:]:
        if t - filtered[-1] >= MIN_GAP:
            filtered.append(t)
    return np.array(filtered)

def snap_to_nearest_beat(t, beat_times):
    if len(beat_times) == 0:
        return t
    idx = (np.abs(beat_times - t)).argmin()
    return float(beat_times[idx])

def estimate_chords(audio_path, output_midi_path=None, separate=False, use_btc=True, use_librosa_chroma=True, use_beat_sync=True, use_basic_pitch=True, use_midi_to_chord=False):
    from basic_pitch.inference import predict
    import torch
    
    processing_path = audio_path
    
    # ギター成分抽出モジュール
    if separate:
        try:
            processing_path = separate_guitar(audio_path)
            print(f"[INFO] Using separated audio track: {processing_path}")
        except Exception as e:
            print(f"[WARN] Demucs separation failed, falling back to original: {e}")
            processing_path = audio_path

    print(f"\n{'='*60}")
    print(f"[INFO] Analysis Settings: BTC={use_btc}, Chroma={use_librosa_chroma}, MIDI2Chord={use_midi_to_chord}, BeatSync={use_beat_sync}, BasicPitch={use_basic_pitch}")
    print(f"{'='*60}")
    
    midi_bytes = None
    midi_data = None
    if use_basic_pitch:
        print("[1/4] Basic Pitch: Generating high-precision MIDI...")
        model_output, midi_data, note_events = predict(processing_path)
        if output_midi_path:
            midi_data.write(output_midi_path)
            with open(output_midi_path, "rb") as f:
                midi_bytes = f.read()
        else:
            out_buffer = io.BytesIO()
            midi_data.write(out_buffer)
            midi_bytes = out_buffer.getvalue()
    else:
        print("[1/4] Basic Pitch: Skipped (MIDI will not be generated)")
        
    # ドラムが含まれるオリジナル音源からしっかりしたビート（拍）を全抽出
    if use_beat_sync:
        beat_times = get_beat_times(audio_path)
    else:
        print("[INFO] Beat Sync: Skipped. Using fixed 0.5s intervals.")
        duration = librosa.get_duration(path=audio_path)
        beat_times = np.arange(0, duration, 0.5)
        if beat_times[-1] < duration:
            beat_times = np.append(beat_times, duration)
    
    frame_chords = []
    btc_frame_probs = []  # List of (time, prob_vector_25) for soft scoring

    if use_btc:
        btc_path = download_btc_if_needed()
        if btc_path not in sys.path:
            sys.path.append(btc_path)
            
        try:
            from utils.hparams import HParams
            from btc_model import BTC_model
            from utils.mir_eval_modules import audio_file_to_features, idx2chord
        except ImportError as e:
            import streamlit as st
            msg = f"【エラー】BTC AI用ライブラリがロードできませんでした。{e}"
            print(msg)
            st.error(msg)
            return [], None
            
        device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        config_path = os.path.join(btc_path, "run_config.yaml")
        config = HParams.load(config_path)
        model_file = os.path.join(btc_path, "test", "btc_model.pt")
        model = BTC_model(config=config.model).to(device)
        
        print("[2/4] BTC: Loading weights...")
        if os.path.isfile(model_file):
            checkpoint = torch.load(model_file, map_location=device, weights_only=False)
            mean = checkpoint['mean']
            std = checkpoint['std']
            model.load_state_dict(checkpoint['model'])
        else:
            print("[ERROR] Pre-trained weights not found.")
            return [], None
            
        print("[3/4] BTC: Extracting audio features (CQT)...")
        try:
            feature, feature_per_second, _ = audio_file_to_features(processing_path, config)
        except Exception as e:
            print(f"[ERROR] Feature extraction failed: {e}")
            return [], None
            
        feature = feature.T
        feature = (feature - mean) / std
        time_unit = feature_per_second
        n_timestep = config.model['timestep']

        num_pad = n_timestep - (feature.shape[0] % n_timestep)
        feature = np.pad(feature, ((0, num_pad), (0, 0)), mode="constant", constant_values=0)
        num_instance = feature.shape[0] // n_timestep
        
        print("[4/4] BTC: Running inference (softmax probabilities)...")
        
        # BTC idx2chord order: [C, C:min, C#, C#:min, ..., B, B:min, N] (25 classes)
        # Build mapping from BTC index → our template index
        # Our template: [C, C#, D, ..., B (0-11 major), Cm, C#m, ..., Bm (12-23 minor), N (24)]
        btc_to_template = np.zeros(25, dtype=int)
        for k in range(12):
            btc_to_template[2 * k] = k          # major
            btc_to_template[2 * k + 1] = 12 + k  # minor
        btc_to_template[24] = 24  # N
        
        with torch.no_grad():
            model.eval()
            feature = torch.tensor(feature, dtype=torch.float32).unsqueeze(0).to(device)
            
            for t in range(num_instance):
                self_attn_output, _ = model.self_attn_layers(feature[:, n_timestep * t:n_timestep * (t + 1), :])
                # Get full softmax probabilities instead of argmax
                logits = model.output_layer.output_projection(self_attn_output)
                probs = torch.softmax(logits, dim=-1).squeeze(0).cpu().numpy()  # (n_timestep, 25)
                
                for i in range(n_timestep):
                    cur_time = float(time_unit) * (n_timestep * t + i)
                    # Remap BTC probabilities to our template ordering
                    remapped = np.zeros(25)
                    for btc_idx in range(25):
                        remapped[btc_to_template[btc_idx]] = probs[i, btc_idx]
                    btc_frame_probs.append((cur_time, remapped))
                    
                    # Also keep hard label for compatibility
                    idx = np.argmax(probs[i])
                    chord_name = idx2chord[idx]
                    if ':min' in chord_name:
                        chord_name = chord_name.replace(':min', 'm')
                    frame_chords.append((cur_time, chord_name))
    else:
        print("[2/4, 3/4, 4/4] BTC: Skipped (User disabled)")
    
    # === コード判定用テンプレート作成 (Librosa / MIDI共通) ===
    maj_temp = np.array([1, 0, 0, 0, 1, 0, 0, 1, 0, 0, 0, 0])
    min_temp = np.array([1, 0, 0, 1, 0, 0, 0, 1, 0, 0, 0, 0])
    templates = []
    librosa_chord_names = []
    notes_list = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']
    
    for i in range(12):
        templates.append(np.roll(maj_temp, i))
        librosa_chord_names.append(notes_list[i])
    for i in range(12):
        templates.append(np.roll(min_temp, i))
        librosa_chord_names.append(notes_list[i] + 'm')
        
    templates.append(np.zeros(12)) # 'N' (無音/判定不能)
    librosa_chord_names.append('N')
    templates = np.array(templates)
    
    norms = np.linalg.norm(templates, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    templates = templates / norms
    
    # === 追加: Librosa Chromaによるコード解析 (HPSS + Multi-Chroma) ===
    librosa_scores = None
    y_proc = sr_proc = None

    if use_librosa_chroma:
        print("[5/5] Librosa: HPSS + Multi-Chroma Feature Extraction...")
        try:
            y_proc, sr_proc = librosa.load(processing_path, sr=22050)
            
            # HPSS: Separate harmonic content from percussive (drums corrupt chroma)
            y_harmonic, _ = librosa.effects.hpss(y_proc)
            
            # CQT chroma: better frequency resolution for harmonic content
            chroma_cqt = librosa.feature.chroma_cqt(y=y_harmonic, sr=sr_proc,
                                                      n_chroma=12, n_octaves=6)
            # CENS chroma: noise-robust, good for structural matching
            chroma_cens = librosa.feature.chroma_cens(y=y_harmonic, sr=sr_proc)
            
            # Align lengths (CENS can differ slightly)
            min_len = min(chroma_cqt.shape[1], chroma_cens.shape[1])
            chroma_cqt = chroma_cqt[:, :min_len]
            chroma_cens = chroma_cens[:, :min_len]
            
            # Fused chroma: weighted combination (CQT more detail, CENS more stable)
            chroma_fused = 0.6 * chroma_cqt + 0.4 * chroma_cens
            
            librosa_scores = np.dot(templates, chroma_fused)  # shape: (25, frames)
        except Exception as e:
            print(f"[WARN] Librosa Chroma analysis failed: {e}")
            librosa_scores = None
    else:
        print("[5/5] Librosa Chroma: Skipped (User disabled)")

    # === Softmax normalization helper ===
    def _softmax(x, temperature=1.0):
        """Apply softmax to convert arbitrary scores into a proper probability distribution."""
        x = np.asarray(x, dtype=np.float64)
        x = x / max(temperature, 1e-8)
        x = x - np.max(x)  # numerical stability
        e = np.exp(x)
        s = np.sum(e)
        if s < 1e-12:
            return np.ones_like(x) / len(x)
        return e / s

    # Weight settings
    w_btc = 5.0 if use_btc else 0.0
    w_librosa = 2.5 if use_librosa_chroma else 0.0
    w_midi = 4.0 if use_midi_to_chord and midi_data else 0.0
    total_w = w_btc + w_librosa + w_midi
    
    if total_w == 0:
        w_btc = 1.0; total_w = 1.0
        
    w_btc /= total_w
    w_librosa /= total_w
    w_midi /= total_w
    
    # Extract note info if MIDI to Chord is used
    all_midi_notes = []
    if use_midi_to_chord and midi_data is not None:
        for inst in midi_data.instruments:
            if inst.is_drum: continue
            for note in inst.notes:
                all_midi_notes.append(note)
    
    # === Per-beat chord scoring ===
    beat_chord_indices = []  # raw per-beat best index (before smoothing)
    beat_score_matrices = []  # full score vectors for smoothing
    
    for i in range(len(beat_times) - 1):
        s_time = beat_times[i]
        e_time = beat_times[i+1]
        
        probs_btc = np.zeros(25)
        probs_librosa = np.zeros(25)
        probs_midi = np.zeros(25)
        
        # 1. BTC Soft Probabilities (averaged over frames in this beat)
        if w_btc > 0 and btc_frame_probs:
            frames_in_beat = [p for t, p in btc_frame_probs if s_time <= t < e_time]
            if frames_in_beat:
                probs_btc = np.mean(frames_in_beat, axis=0)
            else:
                # Fallback: closest frame
                closest = min(btc_frame_probs, key=lambda x: abs(x[0] - (s_time+e_time)/2.0))
                probs_btc = closest[1].copy()
            # Already a probability distribution from softmax, but re-normalize for safety
            probs_btc = _softmax(probs_btc, temperature=0.5)
                    
        # 2. Librosa Probs (normalized via softmax)
        if w_librosa > 0 and librosa_scores is not None:
            start_frame = librosa.time_to_frames(s_time, sr=sr_proc)
            end_frame = librosa.time_to_frames(e_time, sr=sr_proc)
            if end_frame > start_frame:
                raw = np.mean(librosa_scores[:, start_frame:end_frame], axis=1)
                probs_librosa = _softmax(raw, temperature=0.8)
            else:
                probs_librosa = np.ones(25) / 25.0
                
        # 3. MIDI Probs (normalized via softmax)
        if w_midi > 0:
            chroma = np.zeros(12)
            has_notes = False
            for note in all_midi_notes:
                if note.start < e_time and note.end > s_time:
                    overlap = min(e_time, note.end) - max(s_time, note.start)
                    if overlap > 0:
                        chroma[note.pitch % 12] += overlap * note.velocity
                        has_notes = True
            
            if has_notes and np.sum(chroma) > 0:
                chroma_norm = chroma / np.linalg.norm(chroma)
                raw_midi = np.dot(templates, chroma_norm)
                probs_midi = _softmax(raw_midi, temperature=0.8)
            else:
                probs_midi[24] = 1.0  # 'N'
                
        # Combine normalized probability distributions
        combined_scores = (probs_btc * w_btc) + (probs_librosa * w_librosa) + (probs_midi * w_midi)
        beat_score_matrices.append(combined_scores)
        beat_chord_indices.append(np.argmax(combined_scores))
    
    # === Temporal Smoothing (median filter on chord indices) ===
    # Apply a 3-beat median filter to remove isolated 1-beat chord flickers
    smoothed_indices = list(beat_chord_indices)
    if len(smoothed_indices) >= 3:
        for j in range(1, len(smoothed_indices) - 1):
            prev_idx = beat_chord_indices[j - 1]
            curr_idx = beat_chord_indices[j]
            next_idx = beat_chord_indices[j + 1]
            # If this beat disagrees with both neighbors and neighbors agree, override
            if prev_idx == next_idx and curr_idx != prev_idx:
                # Check if the alternative score is reasonably close (within 70% of best)
                alt_score = beat_score_matrices[j][prev_idx]
                best_score = beat_score_matrices[j][curr_idx]
                if alt_score > best_score * 0.5:
                    smoothed_indices[j] = prev_idx
    
    # === Build results with smoothed indices ===
    buffer_results = []
    for i in range(len(beat_times) - 1):
        s_time = beat_times[i]
        e_time = beat_times[i+1]
        chord = librosa_chord_names[smoothed_indices[i]]
            
        if chord != 'N':
            if buffer_results and buffer_results[-1]['chord'] == chord:
                buffer_results[-1]['end'] = float(e_time)
                buffer_results[-1]['duration'] = float(e_time - buffer_results[-1]['start'])
            else:
                buffer_results.append({
                    "start": float(s_time),
                    "end": float(e_time),
                    "duration": float(e_time - s_time),
                    "chord": chord
                })
    
    # === Post-processing: merge very short segments (<0.15s) into neighbors ===
    MIN_DURATION = 0.15
    if len(buffer_results) > 1:
        merged = [buffer_results[0]]
        for seg in buffer_results[1:]:
            if seg['duration'] < MIN_DURATION:
                # Merge into previous segment
                merged[-1]['end'] = seg['end']
                merged[-1]['duration'] = merged[-1]['end'] - merged[-1]['start']
            else:
                merged.append(seg)
        buffer_results = merged

    print("[SUCCESS] Hybrid Analysis Completed!")
    return buffer_results, midi_bytes

def estimate_chords_from_midi(midi_path):
    print(f"\n{'='*60}")
    print(f"[INFO] Midi2Code Mode: Direct MIDI Analysis")
    print(f"{'='*60}")
    
    import pretty_midi
    midi_data = pretty_midi.PrettyMIDI(midi_path)
    
    beats = midi_data.get_beats()
    if len(beats) < 2:
        duration = midi_data.get_end_time()
        beats = np.arange(0, duration, 0.5)
        if duration > beats[-1]:
            beats = np.append(beats, duration)
            
    # Templates for Chord Matching
    maj_temp = np.array([1, 0, 0, 0, 1, 0, 0, 1, 0, 0, 0, 0])
    min_temp = np.array([1, 0, 0, 1, 0, 0, 0, 1, 0, 0, 0, 0])
    templates = []
    notes_list = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']
    chord_names = []
    
    for i in range(12):
        templates.append(np.roll(maj_temp, i))
        chord_names.append(notes_list[i])
    for i in range(12):
        templates.append(np.roll(min_temp, i))
        chord_names.append(notes_list[i] + 'm')
        
    templates.append(np.zeros(12)) # 'N'
    chord_names.append('N')
    templates = np.array(templates)
    
    norms = np.linalg.norm(templates, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    templates = templates / norms
    
    buffer_results = []
    
    all_notes = []
    for inst in midi_data.instruments:
        if inst.is_drum: continue
        all_notes.extend(inst.notes)
        
    # 音符自体が実際に発音される（オンセット）タイミングから、細かな遷移ポイントを抽出する
    note_onsets = [n.start for n in all_notes]
    if note_onsets:
        # 重複や近すぎるタイミング(0.1秒以内)を整理
        note_onsets = np.sort(np.unique(note_onsets))
        refined_edges = []
        for on in note_onsets:
            if not refined_edges or on - refined_edges[-1] >= 0.1:
                refined_edges.append(on)
                
        # 拍のタイミング（beats）と、実際の音符のタイミング（refined_edges）を統合してグリッドを作る
        combined_times = np.sort(np.unique(np.concatenate((beats, refined_edges))))
        
        # さらに、間隔が短すぎる細切れなグリッド（0.15秒未満など。アルペジオのブレ等）は削除する
        final_times = [combined_times[0]]
        for t in combined_times[1:]:
            if t - final_times[-1] >= 0.15:
                final_times.append(t)
                
        beats = np.array(final_times)
    
        # 曲の一番最後までグリッドが届いていなければ追加
        end_time = midi_data.get_end_time()
        if beats[-1] < end_time:
            beats = np.append(beats, end_time)

    print("[INFO] Calculating Chroma over Dynamic MIDI Grid...")
    for i in range(len(beats)-1):
        s_time = beats[i]
        e_time = beats[i+1]
        
        chroma = np.zeros(12)
        has_notes = False
        
        # 実際にその区間で鳴っているすべての音符のエネルギー（Chroma）を計算
        for note in all_notes:
            if note.start < e_time and note.end > s_time:
                overlap = min(e_time, note.end) - max(s_time, note.start)
                if overlap > 0:
                    # ピッチクラス（0:C, 1:C# ... 11:B）ごとに、ベロシティと重なり時間を加算
                    chroma[note.pitch % 12] += overlap * (note.velocity / 127.0)
                    has_notes = True
                    
        chord = 'N'
        if has_notes and np.sum(chroma) > 0:
            chroma_norm = chroma / np.linalg.norm(chroma)
            probs = np.dot(templates, chroma_norm)
            best_idx = np.argmax(probs)
            # スレッショルド: 何のテンプレにもほとんど一致しない(単音すぎる等)場合はN判定にする
            if probs[best_idx] > 0.4:  
                chord = chord_names[best_idx]
            
        # N（判定不能/無音）を含めずに、そのまま直前のコードを維持するか新規追加する
        if chord != 'N':
            if buffer_results and buffer_results[-1]['chord'] == chord:
                buffer_results[-1]['end'] = float(e_time)
                buffer_results[-1]['duration'] = float(e_time - buffer_results[-1]['start'])
            else:
                buffer_results.append({
                    "start": float(s_time),
                    "end": float(e_time),
                    "duration": float(e_time - s_time),
                    "chord": chord
                })
        else:
            # 音が一時的に途切れたりNになった場合でも、「ギターのコード弾き」の観点では
            # 無音区間を作らず前のコードの余韻として継続させた方がTab譜としての遷移が自然になる
            if buffer_results:
                buffer_results[-1]['end'] = float(e_time)
                buffer_results[-1]['duration'] = float(e_time - buffer_results[-1]['start'])
                
    print(f"[SUCCESS] Analyzed {len(buffer_results)} chord segments.")
    return buffer_results

def synthesize_midi_to_wav(midi_path, wav_path):
    print("[INFO] Synthesizing audio preview from MIDI...")
    import pretty_midi
    from scipy.io import wavfile
    midi_data = pretty_midi.PrettyMIDI(midi_path)
    
    # 44.1kHz FS
    audio_data = midi_data.synthesize(fs=44100)
    
    max_val = np.max(np.abs(audio_data))
    if max_val > 0:
        audio_data = np.int16(audio_data / max_val * 32767)
    else:
        audio_data = np.int16(audio_data)
        
    wavfile.write(wav_path, 44100, audio_data)
    print("[SUCCESS] Audio preview generated.")
