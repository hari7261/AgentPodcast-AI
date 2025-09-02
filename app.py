import gradio as gr
import google.generativeai as genai
from gtts import gTTS
import pyttsx3
import tempfile
import os
from uuid import uuid4
import time
import asyncio
from pydub import AudioSegment
try:
    import edge_tts
    EDGE_TTS_AVAILABLE = True
except ImportError:
    EDGE_TTS_AVAILABLE = False
    print("Edge TTS not available, using fallback options")

# Voice configurations for different speakers
VOICE_CONFIGS = {
    "2_speakers": [
        {"name": "Alex", "voice": "en-US-AriaNeural", "gender": "female"},
        {"name": "Brian", "voice": "en-US-GuyNeural", "gender": "male"}
    ],
    "3_speakers": [
        {"name": "Sarah", "voice": "en-US-JennyNeural", "gender": "female"},
        {"name": "Mike", "voice": "en-US-BrandonNeural", "gender": "male"},
        {"name": "Emma", "voice": "en-US-AriaNeural", "gender": "female"}
    ],
    "4_speakers": [
        {"name": "Sarah", "voice": "en-US-JennyNeural", "gender": "female"},
        {"name": "Mike", "voice": "en-US-BrandonNeural", "gender": "male"},
        {"name": "Emma", "voice": "en-US-AriaNeural", "gender": "female"},
        {"name": "David", "voice": "en-US-GuyNeural", "gender": "male"}
    ]
}

# Initialize Gemini client
client = None

def init_gemini(api_key):
    """Initialize Gemini client with API key"""
    global client
    if api_key and api_key.strip():
        try:
            genai.configure(api_key=api_key)
            client = genai.GenerativeModel('gemini-1.5-flash')
            return "✅ Gemini API connected successfully!"
        except Exception as e:
            return f"❌ Gemini API error: {str(e)}"
    return "ℹ️ Add Gemini API key for AI-powered conversations"

def generate_with_gtts(text, filename):
    """Generate speech using Google's gTTS"""
    try:
        tts = gTTS(text=text, lang='en', slow=False)
        tts.save(filename)
        return filename, None
    except Exception as e:
        return None, f"gTTS Error: {str(e)}"

def generate_with_pyttsx3(text, filename):
    """Generate speech using system's TTS engine"""
    try:
        engine = pyttsx3.init()
        engine.setProperty('rate', 180)
        engine.setProperty('volume', 0.9)
        
        voices = engine.getProperty('voices')
        if voices:
            for voice in voices:
                if 'female' in voice.name.lower() or 'zira' in voice.name.lower():
                    engine.setProperty('voice', voice.id)
                    break
        
        engine.save_to_file(text, filename)
        engine.runAndWait()
        return filename, None
    except Exception as e:
        return None, f"pyttsx3 Error: {str(e)}"

async def generate_with_edge_tts(text, voice, filename):
    """Generate speech using Microsoft Edge TTS with specific voice"""
    if not EDGE_TTS_AVAILABLE:
        return None, "Edge TTS not available"
    
    try:
        communicate = edge_tts.Communicate(text, voice)
        # Save as MP3 since that's Edge TTS default format
        mp3_filename = filename.replace('.wav', '.mp3')
        await communicate.save(mp3_filename)
        return mp3_filename, None
    except Exception as e:
        return None, f"Edge TTS Error: {str(e)}"

def generate_podcast_script(text, speaker_count, use_gemini):
    """Generate a podcast script with multiple speakers"""
    if use_gemini and client:
        try:
            voice_config = VOICE_CONFIGS[f"{speaker_count}_speakers"]
            speaker_names = [config["name"] for config in voice_config]
            
            prompt = f"""Create an engaging podcast conversation between {speaker_count} hosts: {', '.join(speaker_names)}.
            
            Transform this text into a natural conversation where each speaker contributes meaningfully.
            
            Guidelines:
            - Make it sound like a real podcast discussion
            - Each speaker should have distinct perspectives
            - Include natural transitions and interactions
            - Keep it under 2000 characters total
            - Use speaker names clearly (e.g., "Sarah: Hello everyone...")
            
            Original text: {text[:2500]}
            
            Format the output with clear speaker labels like:
            {speaker_names[0]}: [text]
            {speaker_names[1] if len(speaker_names) > 1 else speaker_names[0]}: [text]
            etc."""
            
            response = client.generate_content(prompt)
            return response.text
        except Exception as e:
            return f"AI generation failed: {str(e)}. Using original text."
    
    # Fallback: simple text with speaker distribution
    return text[:1500] + ("..." if len(text) > 1500 else "")

def parse_script_for_speakers(script, speaker_count):
    """Parse the script to extract speaker parts"""
    try:
        voice_config = VOICE_CONFIGS[f"{speaker_count}_speakers"]
        speaker_names = [config["name"] for config in voice_config]
        
        parts = []
        lines = script.split('\n')
        current_speaker = 0
        current_text = ""
        
        # First, try to find explicit speaker labels
        for line in lines:
            line = line.strip()
            if not line:
                continue
                
            # Check if line starts with a speaker name
            speaker_found = False
            for i, name in enumerate(speaker_names):
                if line.lower().startswith(f"{name.lower()}:"):
                    if current_text.strip():
                        parts.append((current_text.strip(), current_speaker))
                    current_speaker = i
                    current_text = line[len(name)+1:].strip()
                    speaker_found = True
                    break
            
            if not speaker_found:
                current_text += " " + line
        
        if current_text.strip():
            parts.append((current_text.strip(), current_speaker))
        
        # If no explicit speakers were found, intelligently distribute text
        if not parts or len(parts) < 2:
            print(f"No explicit speakers found, distributing text among {speaker_count} speakers")
            parts = []
            
            # Split into sentences and distribute
            sentences = []
            for delimiter in ['. ', '! ', '? ']:
                if delimiter in script:
                    sentences = script.split(delimiter)
                    # Add back the delimiter except for the last sentence
                    for i in range(len(sentences) - 1):
                        sentences[i] += delimiter.strip()
                    break
            
            if not sentences:
                sentences = [script]
            
            # Remove empty sentences
            sentences = [s.strip() for s in sentences if s.strip()]
            
            if len(sentences) >= speaker_count:
                # Distribute sentences among speakers
                sentences_per_speaker = len(sentences) // speaker_count
                remainder = len(sentences) % speaker_count
                
                start_idx = 0
                for i in range(speaker_count):
                    # Give extra sentences to first speakers if there's remainder
                    num_sentences = sentences_per_speaker + (1 if i < remainder else 0)
                    
                    if start_idx < len(sentences):
                        end_idx = min(start_idx + num_sentences, len(sentences))
                        speaker_sentences = sentences[start_idx:end_idx]
                        
                        if speaker_sentences:
                            speaker_text = ' '.join(speaker_sentences)
                            parts.append((speaker_text, i))
                            print(f"Speaker {speaker_names[i]}: {len(speaker_sentences)} sentences")
                        
                        start_idx = end_idx
            else:
                # If we have fewer sentences than speakers, alternate between first two speakers
                for i, sentence in enumerate(sentences):
                    speaker_idx = i % min(speaker_count, 2)  # Alternate between first 2 speakers
                    parts.append((sentence, speaker_idx))
        
        # Ensure we have content and speakers are properly assigned
        if not parts:
            parts = [(script, 0)]
        
        # Print debug info
        print(f"Generated {len(parts)} parts for {speaker_count} speakers:")
        for i, (text, speaker_idx) in enumerate(parts):
            speaker_name = speaker_names[speaker_idx]
            print(f"  Part {i+1}: {speaker_name} - {text[:60]}...")
        
        return parts
        
    except Exception as e:
        print(f"Error parsing script: {e}")
        return [(script, 0)]

async def generate_multi_speaker_audio(script_parts, speaker_count):
    """Generate multi-speaker podcast audio"""
    if not EDGE_TTS_AVAILABLE:
        return None, "Edge TTS not available for multi-speaker"
    
    try:
        voice_config = VOICE_CONFIGS[f"{speaker_count}_speakers"]
        audio_files = []
        
        print(f"Generating audio for {len(script_parts)} parts with {speaker_count} speakers")
        
        for i, (speaker_text, speaker_idx) in enumerate(script_parts):
            voice = voice_config[speaker_idx]["voice"]
            speaker_name = voice_config[speaker_idx]["name"]
            temp_filename = f"temp_speaker_{i}_{speaker_name}_{uuid4().hex[:8]}.mp3"
            
            print(f"Part {i+1}: {speaker_name} ({voice}) says: {speaker_text[:50]}...")
            
            result, error = await generate_with_edge_tts(speaker_text, voice, temp_filename)
            if result:
                audio_files.append(temp_filename)
                print(f"✅ Generated audio for {speaker_name}")
            else:
                print(f"❌ Error generating voice for {speaker_name}: {error}")
                # Cleanup and return error
                for f in audio_files:
                    try:
                        os.unlink(f)
                    except:
                        pass
                return None, f"Error generating voice for {speaker_name}: {error}"
        
        # Combine all audio files
        if len(audio_files) > 1:
            print(f"Combining {len(audio_files)} audio files...")
            combined_audio = AudioSegment.empty()
            
            for i, audio_file in enumerate(audio_files):
                try:
                    # Load the audio segment - auto-detect format
                    segment = AudioSegment.from_file(audio_file)
                    
                    # Add the segment to combined audio
                    combined_audio += segment
                    
                    # Add a small pause between speakers (0.5 seconds)
                    if i < len(audio_files) - 1:  # Don't add pause after last segment
                        pause = AudioSegment.silent(duration=500)  # 500ms pause
                        combined_audio += pause
                    
                    print(f"✅ Added segment {i+1}")
                except Exception as e:
                    print(f"❌ Error processing audio file {audio_file}: {e}")
            
            # Save combined audio
            output_filename = f"combined_podcast_{uuid4().hex[:8]}.wav"
            combined_audio.export(output_filename, format="wav")
            
            # Cleanup temporary files
            for f in audio_files:
                try:
                    os.unlink(f)
                    print(f"🗑️ Cleaned up {f}")
                except:
                    pass
            
            print(f"✅ Combined audio saved as {output_filename}")
            return output_filename, None
            
        elif len(audio_files) == 1:
            # Single audio file, just return it
            return audio_files[0], None
        else:
            return None, "No audio files generated"
        
    except Exception as e:
        print(f"❌ Multi-speaker generation error: {str(e)}")
        return None, f"Multi-speaker generation error: {str(e)}"

def create_podcast(text, use_gemini, tts_engine, speaker_count, progress=gr.Progress()):
    """Main function to create podcast from text with multiple speakers"""
    try:
        progress(0.1, "Starting processing...")
        
        if not text.strip():
            return None, "❌ Please enter some text first!", ""
        
        progress(0.3, "Generating podcast script...")
        podcast_script = generate_podcast_script(text, speaker_count, use_gemini)
        
        progress(0.5, "Parsing script for speakers...")
        script_parts = parse_script_for_speakers(podcast_script, speaker_count)
        
        progress(0.7, "Generating audio...")
        
        # Generate audio based on engine choice
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp_file:
            temp_filename = tmp_file.name
        
        if tts_engine == "Multi-Speaker (Edge TTS)" and speaker_count > 1 and EDGE_TTS_AVAILABLE:
            # Use Edge TTS for multi-speaker
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                audio_file, error = loop.run_until_complete(
                    generate_multi_speaker_audio(script_parts, speaker_count)
                )
            finally:
                loop.close()
        elif tts_engine == "gTTS (Online)":
            full_text = " ".join([part[0] for part in script_parts])
            audio_file, error = generate_with_gtts(full_text, temp_filename)
        else:  # pyttsx3
            full_text = " ".join([part[0] for part in script_parts])
            audio_file, error = generate_with_pyttsx3(full_text, temp_filename)
        
        if error:
            return None, f"❌ {error}", podcast_script
        
        progress(0.9, "Finalizing...")
        
        # Read the generated audio file
        with open(audio_file, 'rb') as f:
            audio_data = f.read()
        
        # Clean up
        try:
            os.unlink(audio_file)
        except:
            pass
        
        progress(1.0, "Complete!")
        return audio_data, "✅ Podcast generated successfully!", podcast_script
        
    except Exception as e:
        return None, f"❌ Audio generation failed: {str(e)}", ""

def get_speaker_info(speaker_count):
    """Get speaker information for display"""
    if speaker_count == 1:
        return "**Single Speaker Mode**: Solo narration with one voice"
    
    voice_config = VOICE_CONFIGS[f"{speaker_count}_speakers"]
    info = f"**{speaker_count} Speaker Mode**:\n"
    
    for i, config in enumerate(voice_config):
        info += f"🎤 **{config['name']}** ({config['gender']} voice)\n"
    
    return info

# Create the Gradio interface
def create_interface():
    with gr.Blocks(title="🎙️ Multi-Speaker Podcast Generator", theme=gr.themes.Soft()) as demo:
        gr.Markdown("# 🎙️ Multi-Speaker Podcast Generator")
        gr.Markdown("Transform your text into engaging podcast conversations with multiple realistic voices!")
        
        with gr.Row():
            with gr.Column(scale=2):
                # API Configuration
                gr.Markdown("## 🔑 API Configuration")
                api_key = gr.Textbox(
                    label="Gemini API Key (Optional)",
                    type="password",
                    placeholder="Enter your Google Gemini API key...",
                    info="Get a free key from https://aistudio.google.com/"
                )
                api_status = gr.Textbox(
                    label="API Status",
                    interactive=False,
                    value="ℹ️ Add Gemini API key for AI-powered conversations"
                )
                
                # Input Text
                gr.Markdown("## 📝 Input Text")
                input_text = gr.Textbox(
                    label="Your Content",
                    placeholder="Paste your article, blog post, or any text here...",
                    lines=6
                )
                
                # Configuration
                gr.Markdown("## ⚙️ Configuration")
                speaker_count = gr.Radio(
                    label="Number of Speakers",
                    choices=[1, 2, 3, 4],
                    value=2,
                    info="Choose how many voices for your podcast"
                )
                
                use_gemini = gr.Checkbox(
                    label="Use AI for conversation generation",
                    value=True,
                    info="Creates natural conversations (requires API key)"
                )
                
                tts_engine = gr.Radio(
                    label="Voice Engine",
                    choices=[
                        "Multi-Speaker (Edge TTS)",
                        "gTTS (Online)", 
                        "pyttsx3 (Offline)"
                    ],
                    value="Multi-Speaker (Edge TTS)" if EDGE_TTS_AVAILABLE else "gTTS (Online)",
                    info="Edge TTS provides the most realistic conversations"
                )
                
                # Generate Button
                generate_btn = gr.Button(
                    "🎙️ Generate Podcast",
                    variant="primary",
                    size="lg"
                )
            
            with gr.Column(scale=1):
                # Speaker Info
                speaker_info = gr.Markdown(
                    get_speaker_info(2),
                    label="Speaker Information"
                )
        
        # Status and Results
        status_msg = gr.HTML(
            value="<div style='padding: 10px; background: #e3f2fd; border-radius: 5px; color: #1976d2;'>Ready to generate your podcast!</div>"
        )
        
        with gr.Row():
            audio_output = gr.Audio(
                label="Generated Podcast",
                visible=False
            )
            download_btn = gr.DownloadButton(
                "⬇️ Download Podcast",
                visible=False
            )
        
        script_output = gr.Textbox(
            label="Generated Script",
            lines=8,
            visible=False
        )
        
        # Event handlers
        def update_status(message, success=True):
            color = "#1976d2" if success else "#d32f2f"
            bg_color = "#e3f2fd" if success else "#ffebee"
            return f"<div style='padding: 10px; background: {bg_color}; border-radius: 5px; color: {color};'>{message}</div>"
        
        def generate_podcast_wrapper(text, use_gemini, tts_engine, speaker_count, progress=gr.Progress()):
            audio_data, message, script = create_podcast(text, use_gemini, tts_engine, speaker_count, progress)
            
            status_html = update_status(message, success=audio_data is not None)
            
            if audio_data:
                # Save audio to temporary file
                filename = f"podcast_{speaker_count}speakers_{uuid4().hex[:8]}.wav"
                filepath = os.path.join(tempfile.gettempdir(), filename)
                
                with open(filepath, 'wb') as f:
                    f.write(audio_data)
                
                return [
                    status_html,
                    gr.Audio(value=filepath, visible=True),
                    gr.DownloadButton(value=filepath, visible=True),
                    gr.Textbox(value=script, visible=True)
                ]
            else:
                return [
                    status_html,
                    gr.Audio(visible=False),
                    gr.DownloadButton(visible=False),
                    gr.Textbox(visible=False)
                ]
        
        # Connect events
        api_key.change(init_gemini, inputs=api_key, outputs=api_status)
        
        speaker_count.change(
            get_speaker_info,
            inputs=speaker_count,
            outputs=speaker_info
        )
        
        generate_btn.click(
            generate_podcast_wrapper,
            inputs=[input_text, use_gemini, tts_engine, speaker_count],
            outputs=[status_msg, audio_output, download_btn, script_output]
        )
    
    return demo

if __name__ == "__main__":
    demo = create_interface()
    demo.launch(
        server_name="0.0.0.0",
        server_port=7860,
        share=False,
        show_error=True
    )
