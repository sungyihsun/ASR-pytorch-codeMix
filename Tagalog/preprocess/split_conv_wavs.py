import os
from pydub import AudioSegment

def split_wav(wav_path, out_dir, triples):
    audio = AudioSegment.from_file(wav_path, "wav")
    for (fid, t1, t2) in triples:
        new_wav_path = os.path.join(out_dir, fid+'.wav')
        t1_ms = t1*1000
        t2_ms = t2*1000
        newAudio = audio[t1_ms:t2_ms]
        newAudio.export(new_wav_path, format="wav")

def main():
    parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    data_dir = os.path.join(parent_dir, 'data')

    raw_wav_dir = os.path.join(data_dir, 'raw_wav')
    new_wav_dir = os.path.join(data_dir, 'wav')
    if not os.path.exists(new_wav_dir):
        os.makedirs(new_wav_dir)
    conv_txt_path = os.path.join(data_dir, 'text', 'conv.txt')
    
    with open(conv_txt_path, 'r') as inf:
        lines = inf.readlines()
    
    wav_to_time = {} # {wav_file : (fid, t1, t2)}
    for l in lines:
        l = l.strip()
        l_list = l.split()
        tot_fid = l_list[0]
        t2_start_index = tot_fid.rfind('_')+1
        t2 = float(tot_fid[t2_start_index:].replace('p', '.'))
        t1_start_index = tot_fid.rfind('_', 0, t2_start_index-1)+1
        t1 = float(tot_fid[t1_start_index:t2_start_index-1].replace('p', '.'))
        fid = tot_fid[:t1_start_index-1]
        wav_file = fid+'.wav'
        triple = (tot_fid, t1, t2)
        if wav_file in wav_to_time:
            wav_to_time[wav_file].append(triple)
        else:
            wav_to_time[wav_file] = [triple]
    
    for wav_file in wav_to_time:
        print(wav_file)
        wav_path = os.path.join(raw_wav_dir, wav_file)
        split_wav(wav_path, new_wav_dir, wav_to_time[wav_file])

if __name__ == '__main__':
    main()