import streamlit as st
import tempfile
import os
import sys
import json
import base64
import streamlit.components.v1 as components

# Add src to path
sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))

try:
    from src.chord_analyser import estimate_chords, estimate_chords_from_midi, synthesize_midi_to_wav
    from src.tab_generator import generate_ascii_tab, get_chord_fingering, format_tab_string
except ImportError:
    # Fallback if running from a different workdir context
    import sys
    sys.path.append('.') 
    from src.chord_analyser import estimate_chords, estimate_chords_from_midi, synthesize_midi_to_wav
    from src.tab_generator import generate_ascii_tab, get_chord_fingering, format_tab_string

st.set_page_config(page_title="Code2Tab", layout="wide")

st.title("🎸 Code2Tab")
st.markdown("音声ファイルをアップロード → AI + 音響解析のハイブリッド推定でコード進行を推定 → ギタータブ譜 & MIDIを生成します。")

# Sidebar
st.sidebar.header("設定")
tab_mode = st.sidebar.radio("コードモード", ("Standard", "Power Chord"), help="Standard: 通常のコードフォーム\nPower Chord: パワーコードのみ")
# use_demucs = st.sidebar.checkbox("🎸 ギター音源のみを自動抽出して解析 (高精度/時間がかかります)", value=True)
st.sidebar.warning("※現在Python 3.14環境のため音源分離機能(Demucs)は無効化されています。")

st.sidebar.markdown("---")
st.sidebar.subheader("⚙️ 解析精度")

analysis_level = st.sidebar.slider(
    "解析レベル",
    min_value=1, max_value=3, value=2, step=1,
    format="%d",
    help="右に行くほど高精度になりますが、処理時間が長くなります。"
)

_level_labels = {
    1: "⚡ 高速モード",
    2: "⚖️ バランスモード（推奨）",
    3: "🎯 高精度モード",
}
_level_details = {
    1: "**BTC AI推論のみ** — 最も高速。Transformer AIだけでコードを推定します。\n\n"
       "⚠️ 音響的な裏付けがないため、似た響きのコード (例: C と Am) を取り違える場合があります。\n\n"
       "⚠️ MIDI生成は行われません。",
    2: "**BTC AI + Librosa音響補正** — 速度と精度のバランスが最も良い構成です。\n\n"
       "AIの推論をHPSS(ハーモニック分離) + Chroma(倍音)解析で補正します。\n\n"
       "⚠️ HPSS処理が追加されるため、レベル1より少し遅くなります。\n\n"
       "⚠️ MIDI生成は行われません。",
    3: "**BTC AI + Librosa音響補正 + MIDI逆算** — 3つのエンジンで多数決。最も正確です。\n\n"
       "Basic PitchでMIDIを生成し、音楽理論ベースでもコードを逆算して照合します。\n\n"
       "⚠️ Basic Pitchの処理が追加されるため、**処理時間が大幅に増加**します（目安: 2〜5倍）。\n\n"
       "✅ MIDIダウンロード機能が有効になります。",
}

st.sidebar.markdown(f"**{_level_labels[analysis_level]}**")

with st.sidebar.expander("ℹ️ このレベルの詳細・注意点", expanded=False):
    st.markdown(_level_details[analysis_level])

# Map slider level to engine flags
use_btc = analysis_level >= 1
use_librosa_chroma = analysis_level >= 2
use_basic_pitch = analysis_level >= 3
use_midi_to_chord = analysis_level >= 3
use_beat_sync = True  # always use beat sync (fixed intervals are worse)

# Mode mapping
mode_key = 'power' if tab_mode == "Power Chord" else 'standard'

uploaded_file = st.file_uploader("音声・MIDIファイルをアップロード (mp3, wav, mid, midi)", type=["mp3", "wav", "mid", "midi"])

if uploaded_file is not None:
    # st.audio(uploaded_file, format='audio/wav') # Remove standard player to use custom one
    
    if st.button("解析スタート"):
        
        ext = uploaded_file.name.split('.')[-1].lower()
        is_midi = ext in ['mid', 'midi']
        
        # Save temp file
        with tempfile.NamedTemporaryFile(delete=False, suffix=f".{ext}") as tmp_file:
            tmp_file.write(uploaded_file.getvalue())
            file_path = tmp_file.name
            
        audio_path = file_path # Default mapping, overridden if MIDI
        wav_path = None

        try:
            if is_midi:
                with st.spinner('MIDIを解析＆音声を合成中... (Midi2Codeモード)'):
                    chords_data = estimate_chords_from_midi(file_path)
                    
                    with open(file_path, "rb") as f:
                        midi_bytes = f.read()
                        
                    # Synthesize preview audio
                    wav_path = file_path + "_synth.wav"
                    synthesize_midi_to_wav(file_path, wav_path)
                    audio_path = wav_path # Route audio player to the synthesized WAV
            else:
                with st.spinner('音声を解析中... (コンソールに進捗が表示されます)'):
                    # Estimate Chords (returns chords_data, midi_bytes)
                    chords_data, midi_bytes = estimate_chords(
                        file_path, 
                        separate=False,
                        use_btc=use_btc,
                        use_librosa_chroma=use_librosa_chroma,
                        use_beat_sync=use_beat_sync,
                        use_basic_pitch=use_basic_pitch,
                        use_midi_to_chord=use_midi_to_chord
                    )
            
            if not chords_data:
                st.error("コード進行を検出できませんでした。音声ファイルを確認してください。")
            else:
                st.success(f"解析完了！ {len(chords_data)} 個のコードセグメントを検出しました。")
                
                # --- MIDI Download Button ---
                if midi_bytes:
                    st.download_button(
                        label="🎹 MIDIファイルをダウンロード",
                        data=midi_bytes,
                        file_name=f"{uploaded_file.name}_chords.mid",
                        mime="audio/midi"
                    )
                
                # --- Custom Audio Player with Synchronized Tab ---
                st.subheader("🎵 プレイヤー & タブ譜同期")
                st.info("再生ボタンを押すと、現在位置のタブ譜がハイライトされます。カードをクリックするとその位置にジャンプします。")

                # Prepare data for HTML
                with open(audio_path, "rb") as f:
                    audio_bytes = f.read()
                audio_base64 = base64.b64encode(audio_bytes).decode('utf-8')
                mime_type = "audio/mp3" if audio_path.endswith(".mp3") else "audio/wav"
                
                # Add tab visual to data
                for segment in chords_data:
                    fingering = get_chord_fingering(segment['chord'], mode=mode_key)
                    segment['tab_visual'] = format_tab_string(fingering)
                    segment['fingering'] = fingering # Pass fingering for audio synthesis

                chords_json = json.dumps(chords_data)
                
                # HTML/JS Code
                html_code = f"""
                <style>
                    .container {{
                        font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif;
                        padding: 10px;
                        background-color: #f0f2f6; 
                        border-radius: 10px;
                        color: #31333F;
                    }}
                    audio {{
                        width: 100%;
                        margin-bottom: 20px;
                        outline: none;
                    }}
                    .chord-timeline {{
                        display: flex;
                        flex-wrap: nowrap;
                        overflow-x: auto;
                        gap: 12px;
                        padding: 20px 10px;
                        background: #ffffff;
                        border: 1px solid #ddd;
                        border-radius: 5px;
                        align-items: flex-start;
                        /* Custom Scrollbar */
                        scrollbar-width: thin;
                        scrollbar-color: #888 #f1f1f1;
                    }}
                    .chord-timeline::-webkit-scrollbar {{
                        height: 8px;
                    }}
                    .chord-timeline::-webkit-scrollbar-thumb {{
                        background: #888; 
                        border-radius: 4px;
                    }}
                    .chord-card {{
                        background: #ffffff;
                        border: 2px solid #ddd;
                        border-radius: 8px;
                        padding: 12px;
                        min-width: 120px;
                        flex-shrink: 0;
                        text-align: center;
                        cursor: pointer;
                        transition: all 0.2s;
                        position: relative;
                        display: flex;
                        flex-direction: column;
                        align-items: center;
                    }}
                    .chord-card:hover {{
                        border-color: #ff4b4b;
                    }}
                    .chord-card.active {{
                        background-color: #ff4b4b;
                        color: white !important;
                        border-color: #ff4b4b;
                        transform: scale(1.05);
                        z-index: 10;
                        box-shadow: 0 4px 10px rgba(0,0,0,0.3);
                    }}
                    .chord-card.active .chord-name {{
                        color: white;
                    }}
                    .chord-card.active .tab-visual {{
                        background: rgba(255, 255, 255, 0.2);
                        color: white;
                    }}
                    .chord-card.active .chord-time {{
                        color: #ffe8e8;
                    }}
                    .chord-name {{
                        font-size: 1.4em;
                        font-weight: bold;
                        color: #31333F;
                        margin-bottom: 5px;
                    }}
                    .tab-visual {{
                        font-family: 'Courier New', Courier, monospace;
                        font-size: 12px;
                        white-space: pre;
                        line-height: 1.1;
                        background: #f5f5f5;
                        padding: 6px;
                        border-radius: 4px;
                        color: #333;
                        margin-bottom: 5px;
                        font-weight: bold;
                    }}
                    .chord-time {{
                        font-size: 0.8em;
                        color: #888;
                        margin-top: auto;
                    }}
                    .position-btns {{
                        display: flex;
                        gap: 4px;
                        margin-top: 4px;
                    }}
                    .position-btns button {{
                        background: #eee;
                        border: 1px solid #ccc;
                        border-radius: 4px;
                        cursor: pointer;
                        font-size: 0.85em;
                        padding: 2px 8px;
                        line-height: 1.2;
                        transition: background 0.15s;
                    }}
                    .position-btns button:hover {{
                        background: #ddd;
                    }}
                    .chord-card.active .position-btns button {{
                        background: rgba(255,255,255,0.3);
                        border-color: rgba(255,255,255,0.5);
                        color: white;
                    }}
                    .chord-card.active .position-btns button:hover {{
                        background: rgba(255,255,255,0.5);
                    }}
                    .timing-row {{
                        display: flex;
                        align-items: center;
                        gap: 3px;
                        margin-top: 4px;
                        font-size: 0.75em;
                    }}
                    .timing-row button {{
                        background: #eee;
                        border: 1px solid #ccc;
                        border-radius: 3px;
                        cursor: pointer;
                        font-size: 0.9em;
                        padding: 1px 5px;
                        line-height: 1.2;
                    }}
                    .timing-row button:hover {{
                        background: #ddd;
                    }}
                    .timing-row .timing-val {{
                        min-width: 42px;
                        text-align: center;
                        font-family: monospace;
                    }}
                    .chord-card.active .timing-row button {{
                        background: rgba(255,255,255,0.3);
                        border-color: rgba(255,255,255,0.5);
                        color: white;
                    }}
                    .chord-card.active .timing-row .timing-val {{
                        color: #ffe8e8;
                    }}
                    .offset-bar {{
                        display: flex;
                        align-items: center;
                        gap: 10px;
                        background: #fff;
                        padding: 6px 12px;
                        border-radius: 5px;
                        border: 1px solid #ccc;
                        font-size: 0.9em;
                        font-weight: bold;
                    }}
                    .offset-bar .offset-val {{
                        font-family: monospace;
                        min-width: 55px;
                        text-align: center;
                    }}
                </style>
                
                <div class="container">
                    <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom: 20px;">
                        <audio id="player" controls style="width: 100%; outline: none; margin-bottom: 0;">
                            <source src="data:{mime_type};base64,{audio_base64}" type="{mime_type}">
                            Your browser does not support audio element.
                        </audio>
                    </div>
                    <div style="display:flex; justify-content:flex-end; align-items:center; gap: 15px; margin-bottom: 10px;">
                        <label style="font-weight:bold; font-size:0.9em; cursor:pointer; background:#fff; padding:6px 10px; border-radius:5px; border:1px solid #ccc; display:flex; align-items:center; gap:8px;">
                            <input type="checkbox" id="synth-sync-toggle" checked>
                            🎧 再生時にコードシンセ音も同時に鳴らす
                        </label>
                        <div style="background:#fff; padding:6px 10px; border-radius:5px; border:1px solid #ccc; display:flex; align-items:center; gap:8px;">
                            <span style="font-size:0.9em; font-weight:bold;">🔊 シンセ音量:</span>
                            <input type="range" id="synth-volume" min="0" max="1" step="0.05" value="0.6" style="width: 100px;">
                        </div>
                    </div>
                    <div style="display:flex; justify-content:flex-end; align-items:center; gap: 15px; margin-bottom: 10px;">
                        <div class="offset-bar">
                            <span>⏱️ 全体オフセット:</span>
                            <button onclick="changeGlobalOffset(-0.1)">-0.1s</button>
                            <button onclick="changeGlobalOffset(-0.05)">-0.05s</button>
                            <span class="offset-val" id="offset-display">0.00s</span>
                            <button onclick="changeGlobalOffset(0.05)">+0.05s</button>
                            <button onclick="changeGlobalOffset(0.1)">+0.1s</button>
                            <button onclick="resetGlobalOffset()" style="font-size:0.85em;">↺</button>
                        </div>
                    </div>
                    
                    <div id="timeline" class="chord-timeline">
                        <!-- JS creates items here -->
                    </div>
                </div>

                <script>
                    const chords = {chords_json};
                    const player = document.getElementById('player');
                    const timeline = document.getElementById('timeline');
                    const syncToggle = document.getElementById('synth-sync-toggle');
                    const volumeSlider = document.getElementById('synth-volume');
                    
                    // Web Audio API Context
                    const AudioContext = window.AudioContext || window.webkitAudioContext;
                    let audioCtx;

                    function playChord(e, fingering) {{
                        if (e) e.stopPropagation(); // Prevent card click (seeking)
                        
                        if (!audioCtx) {{
                            audioCtx = new AudioContext();
                        }}
                        if (audioCtx.state === 'suspended') {{
                            audioCtx.resume();
                        }}

                        // E A D G B e
                        // Note: fingering is [e(0), B(1), G(2), D(3), A(4), E(5)]
                        // Open strings freq in Hz: [329.63, 246.94, 196.00, 146.83, 110.00, 82.41]
                        const openFreqs = [329.63, 246.94, 196.00, 146.83, 110.00, 82.41];
                        
                        // To strum downwards (low E to high e), we iterate backwards from 5 to 0
                        const duration = 1.8;
                        const strumDelay = 0.03;
                        
                        // Use slider value for volume
                        const userBaseVol = parseFloat(volumeSlider.value);
                        // If it's an auto-play (e is null), adjust volume relative to slider so it doesn't clip
                        const baseGain = e ? userBaseVol : userBaseVol * 0.8;

                        for (let i = 5; i >= 0; i--) {{
                            const fret = fingering[i];
                            if (fret === -1) continue; // Muted string

                            const freq = openFreqs[i] * Math.pow(2, fret / 12);
                            const delay = (5 - i) * strumDelay;
                            const startTime = audioCtx.currentTime + delay;

                            const osc = audioCtx.createOscillator();
                            const gainNode = audioCtx.createGain();

                            osc.type = 'triangle'; // Smoother tone
                            osc.frequency.setValueAtTime(freq, startTime);

                            // Apply envelope
                            gainNode.gain.setValueAtTime(0, startTime);
                            gainNode.gain.linearRampToValueAtTime(baseGain, startTime + 0.05); // Attack
                            gainNode.gain.exponentialRampToValueAtTime(0.001, startTime + duration); // Decay

                            osc.connect(gainNode);
                            gainNode.connect(audioCtx.destination);

                            osc.start(startTime);
                            osc.stop(startTime + duration);
                        }}
                    }}

                    // Store original fingerings for reset
                    const originalFingerings = chords.map(c => [...c.fingering]);
                    // Store original timings for reset
                    const originalTimings = chords.map(c => ({{ start: c.start, end: c.end }}));
                    // Global offset
                    let globalOffset = 0;
                    // Per-chord offset
                    const chordOffsets = chords.map(() => 0);

                    function getEffectiveStart(idx) {{
                        return chords[idx].start;
                    }}
                    function getEffectiveEnd(idx) {{
                        return chords[idx].end;
                    }}

                    function changeGlobalOffset(delta) {{
                        globalOffset = Math.round((globalOffset + delta) * 100) / 100;
                        // Apply to all chords
                        for (let i = 0; i < chords.length; i++) {{
                            chords[i].start = Math.max(0, Math.round((originalTimings[i].start + globalOffset + chordOffsets[i]) * 100) / 100);
                            chords[i].end = Math.max(0, Math.round((originalTimings[i].end + globalOffset + chordOffsets[i]) * 100) / 100);
                        }}
                        document.getElementById('offset-display').textContent = (globalOffset >= 0 ? '+' : '') + globalOffset.toFixed(2) + 's';
                        updateAllTimingDisplays();
                    }}

                    function resetGlobalOffset() {{
                        globalOffset = 0;
                        for (let i = 0; i < chords.length; i++) {{
                            chords[i].start = Math.max(0, Math.round((originalTimings[i].start + chordOffsets[i]) * 100) / 100);
                            chords[i].end = Math.max(0, Math.round((originalTimings[i].end + chordOffsets[i]) * 100) / 100);
                        }}
                        document.getElementById('offset-display').textContent = '0.00s';
                        updateAllTimingDisplays();
                    }}

                    function adjustChordTiming(e, idx, delta) {{
                        e.stopPropagation();
                        chordOffsets[idx] = Math.round((chordOffsets[idx] + delta) * 100) / 100;
                        chords[idx].start = Math.max(0, Math.round((originalTimings[idx].start + globalOffset + chordOffsets[idx]) * 100) / 100);
                        chords[idx].end = Math.max(0, Math.round((originalTimings[idx].end + globalOffset + chordOffsets[idx]) * 100) / 100);
                        updateTimingDisplay(idx);
                    }}

                    function resetChordTiming(e, idx) {{
                        e.stopPropagation();
                        chordOffsets[idx] = 0;
                        chords[idx].start = Math.max(0, Math.round((originalTimings[idx].start + globalOffset) * 100) / 100);
                        chords[idx].end = Math.max(0, Math.round((originalTimings[idx].end + globalOffset) * 100) / 100);
                        updateTimingDisplay(idx);
                    }}

                    function updateTimingDisplay(idx) {{
                        const card = document.getElementById('card-' + idx);
                        card.querySelector('.chord-time').textContent = chords[idx].start.toFixed(1) + 's';
                        const valEl = card.querySelector('.timing-val');
                        if (valEl) {{
                            const off = chordOffsets[idx];
                            valEl.textContent = (off >= 0 ? '+' : '') + off.toFixed(2) + 's';
                        }}
                    }}

                    function updateAllTimingDisplays() {{
                        for (let i = 0; i < chords.length; i++) {{
                            updateTimingDisplay(i);
                        }}
                    }}

                    // --- Reset position function ---
                    function resetPosition(e, idx) {{
                        e.stopPropagation();
                        const chord = chords[idx];
                        chord.fingering = [...originalFingerings[idx]];
                        const sNames = ['e', 'B', 'G', 'D', 'A', 'E'];
                        chord.tab_visual = chord.fingering.map((f, i) => {{
                            const fc = f !== -1 ? f : 'x';
                            return sNames[i] + ' |-' + fc + '-|';
                        }}).join('\\n');
                        const card = document.getElementById('card-' + idx);
                        card.querySelector('.tab-visual').textContent = chord.tab_visual;
                    }}

                    // --- Position shift function ---
                    function shiftPosition(e, idx, direction) {{
                        e.stopPropagation();
                        const chord = chords[idx];
                        const nonMuted = chord.fingering.filter(f => f !== -1);
                        if (nonMuted.length === 0) return;
                        // Block shift down if any non-muted fret is already 0
                        if (direction === -1 && nonMuted.some(f => f <= 0)) return;
                        // Block shift up beyond fret 24
                        if (direction === 1 && nonMuted.some(f => f >= 24)) return;

                        chord.fingering = chord.fingering.map(f => f === -1 ? -1 : f + direction);

                        // Regenerate tab_visual
                        const sNames = ['e', 'B', 'G', 'D', 'A', 'E'];
                        chord.tab_visual = chord.fingering.map((f, i) => {{
                            const fc = f !== -1 ? f : 'x';
                            return sNames[i] + ' |-' + fc + '-|';
                        }}).join('\\n');

                        // Update card display
                        const card = document.getElementById('card-' + idx);
                        card.querySelector('.tab-visual').textContent = chord.tab_visual;
                    }}

                    // Render chords
                    let cardElements = [];
                    
                    chords.forEach((c, idx) => {{
                        const el = document.createElement('div');
                        el.className = 'chord-card';
                        el.id = 'card-' + idx;
                        
                        const fingeringStr = JSON.stringify(c.fingering);

                        el.innerHTML = `
                            <div class="chord-title-row" style="display:flex; justify-content:space-between; align-items:center; width:100%; margin-bottom:5px;">
                                <div class="chord-name" style="margin-bottom:0;">${{c.chord}}</div>
                                <button class="play-btn" onclick="playChord(event, chords[${{idx}}].fingering)" style="background:none; border:none; cursor:pointer; font-size:1.2em;" title="このコードの音をプレビュー">🔊</button>
                            </div>
                            <div class="tab-visual">${{c.tab_visual}}</div>
                            <div class="position-btns">
                                <button onclick="shiftPosition(event, ${{idx}}, -1)" title="ポジションを下げる">▼</button>
                                <button onclick="resetPosition(event, ${{idx}})" title="元のポジションに戻す" style="font-size:0.75em;">↺</button>
                                <button onclick="shiftPosition(event, ${{idx}}, 1)" title="ポジションを上げる">▲</button>
                            </div>
                            <div class="timing-row">
                                <button onclick="adjustChordTiming(event, ${{idx}}, -0.1)" title="-0.1s">◀</button>
                                <button onclick="resetChordTiming(event, ${{idx}})" title="個別リセット" style="font-size:0.8em;">↺</button>
                                <button onclick="adjustChordTiming(event, ${{idx}}, 0.1)" title="+0.1s">▶</button>
                                <span class="timing-val">+0.00s</span>
                            </div>
                            <div class="chord-time">${{c.start.toFixed(1)}}s</div>
                        `;
                        
                        // Click to seek (uses live timing)
                        el.onclick = () => {{
                            player.currentTime = chords[idx].start;
                            player.play();
                        }};
                        
                        timeline.appendChild(el);
                        cardElements.push(el);
                    }});
                    
                    // Sync logic
                    let activeIndex = -1;
                    
                    player.ontimeupdate = () => {{
                        const t = player.currentTime;
                        
                        // Find current chord
                        let currentIdx = -1;
                        for(let i=0; i<chords.length; i++) {{
                            if(t >= chords[i].start && t < chords[i].end) {{
                                currentIdx = i;
                                break;
                            }}
                        }}
                        
                        if(currentIdx !== activeIndex) {{
                            if(activeIndex !== -1) {{
                                cardElements[activeIndex].classList.remove('active');
                            }}
                            
                            if(currentIdx !== -1) {{
                                const target = cardElements[currentIdx];
                                target.classList.add('active');
                                
                                // Scroll into view (Horizontal)
                                const containerWidth = timeline.offsetWidth;
                                const cardLeft = target.offsetLeft;
                                const cardWidth = target.offsetWidth;
                                
                                // Center the active card
                                timeline.scrollTo({{
                                    left: cardLeft - (containerWidth / 2) + (cardWidth / 2),
                                    behavior: 'smooth'
                                }});
                                
                                // Play synth sound if playing and toggle is true (use live fingering)
                                if(!player.paused && syncToggle.checked) {{
                                    playChord(null, chords[currentIdx].fingering);
                                }}
                            }}
                            activeIndex = currentIdx;
                        }}
                    }};
                </script>
                """
                
                components.html(html_code, height=470, scrolling=False)

                st.divider()
                
                # Layout for static tab view
                col1, col2 = st.columns([2, 1])
                
                with col1:
                    st.subheader(f"ギタータブ譜 ({tab_mode})")
                    ascii_tab = generate_ascii_tab(chords_data, mode=mode_key)
                    st.code(ascii_tab, language="text")
                
                with col2:
                    st.subheader("コード一覧")
                    unique_chords = sorted(list(set([s['chord'] for s in chords_data])))
                    
                    for chord in unique_chords:
                        fingering = get_chord_fingering(chord, mode=mode_key)
                        visual = format_tab_string(fingering)
                        with st.expander(f"🎸 {chord}", expanded=False):
                            st.code(visual, language="text")
                            play_btn_html = f"""
                            <button onclick="playMiniChord({fingering})" style="padding: 5px 10px; border-radius: 4px; border: 1px solid #ccc; cursor: pointer; background: #eee; font-family: sans-serif;">🔊 音を鳴らす</button>
                            <script>
                                let audioCtx = null;
                                function playMiniChord(fingering) {{
                                    if(!audioCtx) audioCtx = new (window.AudioContext || window.webkitAudioContext)();
                                    if(audioCtx.state === 'suspended') audioCtx.resume();
                                    const openFreqs = [329.63, 246.94, 196.00, 146.83, 110.00, 82.41];
                                    for(let i=5; i>=0; i--) {{
                                        let f = fingering[i];
                                        if(f === -1) continue;
                                        let freq = openFreqs[i] * Math.pow(2, f/12);
                                        let osc = audioCtx.createOscillator();
                                        let gainNode = audioCtx.createGain();
                                        osc.type = 'triangle';
                                        let t = audioCtx.currentTime + (5-i)*0.03;
                                        osc.frequency.setValueAtTime(freq, t);
                                        gainNode.gain.setValueAtTime(0, t);
                                        gainNode.gain.linearRampToValueAtTime(0.3, t + 0.05);
                                        gainNode.gain.exponentialRampToValueAtTime(0.001, t + 1.8);
                                        osc.connect(gainNode);
                                        gainNode.connect(audioCtx.destination);
                                        osc.start(t);
                                        osc.stop(t+1.8);
                                    }}
                                }}
                            </script>
                            """
                            components.html(play_btn_html, height=45)


                            
        except Exception as e:
            st.error(f"エラーが発生しました: {e}")
            import traceback
            st.code(traceback.format_exc())
            
        finally:
            # Cleanup temp files
            try:
                if 'file_path' in locals() and file_path and os.path.exists(file_path):
                    os.remove(file_path)
                if 'wav_path' in locals() and wav_path and os.path.exists(wav_path):
                    os.remove(wav_path)
            except:
                pass

st.markdown("---")
st.markdown("Powered by Streamlit, BTC Transformer, Librosa, Basic Pitch  \n© 2026 yuutti")
