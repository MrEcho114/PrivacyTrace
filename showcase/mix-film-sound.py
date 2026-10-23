"""Retain the original music, add sparse original tactile cues, master to -16 LUFS.

No recorded samples or network services. Requires numpy and ffmpeg. The seed,
event score, source hashes and two-pass loudness measurements ship with the mix.
"""
import hashlib
import json
import math
from pathlib import Path
import re
import subprocess
import wave

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
RATE = 48000
SEED = 305264
SCORES = {
    '90s': ('showcase/privacytrace-90s/assets', 'soundtrack-90s.m4a', 90, [
        (1.65, 'felt', .1, .045), (3.1, 'paper', .35, .025),
        (9.0, 'felt', -.2, .04), (20.7, 'paper', -.45, .035),
        (45.0, 'felt', 0, .045), (60.8, 'paper', -.2, .03),
        (72.0, 'felt', 0, .035), (84.3, 'felt', 0, .04),
    ]),
    'review': ('showcase/privacytrace-review/delivery/assets', 'soundtrack.m4a', 120, [
        (6.8, 'felt', 0, .04), (9.375, 'paper', .3, .025),
        (23.35, 'paper', -.25, .03), (40.625, 'felt', -.25, .04),
        (59.35, 'paper', .4, .025), (65.0, 'felt', 0, .04),
        (90.95, 'paper', -.35, .025), (95.1, 'felt', .35, .03),
        (108.78, 'felt', 0, .04),
    ]),
}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def ffmpeg(args):
    return subprocess.run(['ffmpeg', '-hide_banner', '-y', *args], check=True,
                          capture_output=True, text=True, encoding='utf-8', errors='replace')


def material(kind, rng):
    duration = .5 if kind == 'paper' else .26
    t = np.arange(round(duration * RATE)) / RATE
    noise = rng.standard_normal(len(t))
    freq = np.fft.rfftfreq(len(t), 1/RATE)
    # Paper air and a damped wooden contact share a short, quiet room.
    band = (freq/(freq+600))**2 / (1+(freq/4300)**4)
    air = np.fft.irfft(np.fft.rfft(noise)*band, n=len(t))
    air /= max(float(np.max(np.abs(air))), 1e-9)
    if kind == 'paper':
        signal = air * np.sin(np.pi*t/duration)**2
    else:
        signal = (.8*np.sin(2*np.pi*176*t)*np.exp(-36*t)
                  + .3*air*np.exp(-85*t)) * (1-np.exp(-850*t))
    room = signal.copy()
    for delay, gain in [(.019, .13), (.037, .07), (.061, .035)]:
        n=round(delay*RATE)
        room[n:] += signal[:-n]*gain
    return room


def main():
    for name, (folder, source_name, duration, events) in SCORES.items():
        assets = ROOT/folder
        work = ROOT/'tmp/film-sound'/name
        work.mkdir(parents=True, exist_ok=True)
        rng = np.random.default_rng(SEED)
        samples = np.zeros((duration*RATE, 2), dtype=np.float32)
        for second, kind, pan, gain in events:
            cue = material(kind, rng)*gain
            start = round(second*RATE)
            n=min(len(cue),len(samples)-start)
            angle=(pan+1)*math.pi/4
            samples[start:start+n,0] += cue[:n]*math.cos(angle)
            samples[start:start+n,1] += cue[:n]*math.sin(angle)
        sfx=work/'original-cues.wav'
        with wave.open(str(sfx),'wb') as out:
            out.setnchannels(2);out.setsampwidth(2);out.setframerate(RATE)
            out.writeframes(np.rint(np.clip(samples,-1,1)*32767).astype('<i2').tobytes())
        source=assets/source_name
        target=assets/'soundtrack-polished.m4a'
        mix='[0:a][1:a]amix=inputs=2:normalize=0:dropout_transition=0,'
        first=ffmpeg(['-i',str(source),'-i',str(sfx),'-filter_complex',mix+'loudnorm=I=-16:TP=-2:LRA=4:print_format=json','-f','null','-'])
        measure=json.loads(re.findall(r'\{[^{}]+\}',first.stderr)[-1])
        norm=(f'loudnorm=I=-16:TP=-2:LRA=4:measured_I={measure["input_i"]}'
              f':measured_LRA={measure["input_lra"]}:measured_TP={measure["input_tp"]}'
              f':measured_thresh={measure["input_thresh"]}:offset={measure["target_offset"]}'
              ':linear=true:print_format=json,aresample=48000')
        final=ffmpeg(['-i',str(source),'-i',str(sfx),'-filter_complex',mix+norm,
                      '-c:a','aac','-b:a','192k','-t',str(duration),str(target)])
        measured=json.loads(re.findall(r'\{[^{}]+\}',final.stderr)[-1])
        proof={'film':name,'source':source_name,'sourceSha256':sha(source),
               'output':target.name,'sha256':sha(target),'sampleRate':RATE,
               'seed':SEED,'materials':['synthesized paper air','damped wooden contact'],
               'externalSamples':[], 'events':[{'time':t,'material':m,'pan':p,'gain':g} for t,m,p,g in events],
               'mastering':{'targetLufs':-16,'truePeakCeilingDbtp':-2,'twoPass':True,'measurement':measured}}
        (assets/'sound-provenance.json').write_bytes((json.dumps(proof,ensure_ascii=False,indent=2)+'\n').encode())
        print(name,measured['output_i'],'LUFS',measured['output_tp'],'dBTP',sha(target))


if __name__=='__main__':
    main()
