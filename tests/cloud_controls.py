"""Cloud-only owned controls. No audio/display device is used."""
import functools
import http.server
import os
from pathlib import Path
import shutil
import ssl
import subprocess
import sys
import tempfile
import threading
sys.path.insert(0,str(Path(__file__).parents[1]/'scripts'))
import quality as q

class Handler(http.server.SimpleHTTPRequestHandler):
    def log_message(self,*args):pass


def main():
    binary=shutil.which('ffmpeg')
    if not binary:raise RuntimeError('FFmpeg missing')
    servers=[]
    with tempfile.TemporaryDirectory()as directory:
        root=Path(directory)
        subprocess.run([binary,'-nostdin','-hide_banner','-loglevel','error','-y','-f','lavfi','-i','testsrc=size=320x180:rate=25',
                        '-f','lavfi','-i','anullsrc=r=48000:cl=stereo','-t','4','-c:v','libx264','-preset','ultrafast','-pix_fmt','yuv420p','-c:a','aac','-movflags','+faststart',str(root/'owned.mp4')],check=True)
        subprocess.run([binary,'-nostdin','-hide_banner','-loglevel','error','-i',str(root/'owned.mp4'),'-an','-frames:v','1',str(root/'cover.png')],check=True)
        subprocess.run([binary,'-nostdin','-hide_banner','-loglevel','error','-i',str(root/'owned.mp4'),'-c','copy','-f','hls','-hls_time','1','-hls_list_size','0',str(root/'owned.m3u8')],check=True)
        for name, video, audio in [('short-video',1,4),('short-audio',4,1)]:
            subprocess.run([binary,'-nostdin','-hide_banner','-loglevel','error','-y','-f','lavfi','-t',str(video),'-i','testsrc=size=320x180:rate=25',
                            '-f','lavfi','-t',str(audio),'-i','anullsrc=r=48000:cl=stereo','-c:v','libx264','-preset','ultrafast','-pix_fmt','yuv420p','-c:a','aac','-movflags','+faststart',str(root/(name+'.mp4'))],check=True)
        subprocess.run(['openssl','req','-x509','-newkey','rsa:2048','-nodes','-days','1','-subj','/CN=localhost',
                        '-addext','subjectAltName=DNS:localhost,IP:127.0.0.1','-keyout',str(root/'key.pem'),'-out',str(root/'cert.pem')],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        def server(secure=False):
            instance=http.server.ThreadingHTTPServer(('127.0.0.1',0),functools.partial(Handler,directory=str(root)))
            if secure:
                context=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER);context.load_cert_chain(root/'cert.pem',root/'key.pem');instance.socket=context.wrap_socket(instance.socket,server_side=True)
            threading.Thread(target=instance.serve_forever,daemon=True).start();servers.append(instance)
            return ('https'if secure else'http')+'://localhost:'+str(instance.server_port)
        plain,secure=server(),server(True)
        try:
            result=q.decode(binary,plain+'/owned.mp4',3)
            assert q.grade({'cover':{'ok':True},'decode':result},3)['passed'],result
            hls=q.decode(binary,plain+'/owned.m3u8',3)
            assert q.grade({'cover':{'ok':True},'decode':hls},3)['passed'],hls
            playlist=(root/'owned.m3u8').read_text(encoding='utf-8')
            (root/'tls.m3u8').write_text('\n'.join(plain+'/'+line if line and not line.startswith('#') else line for line in playlist.splitlines())+'\n',encoding='utf-8')
            secure_hls=q.decode(binary,secure+'/tls.m3u8',3,root/'cert.pem')
            assert q.grade({'cover':{'ok':True},'decode':secure_hls},3)['passed'],secure_hls
            for name in ('short-video','short-audio'):
                short=q.decode(binary,plain+'/'+name+'.mp4',3)
                assert not q.grade({'cover':{'ok':True},'decode':short},3)['passed'],short
            missing=q.decode(binary,plain+'/missing.mp4',3)
            assert missing['first_frame_seconds']is None and missing['returncode']!=0,missing
            verified=q.decode(binary,secure+'/owned.mp4',3,root/'cert.pem')
            assert q.grade({'cover':{'ok':True},'decode':verified},3)['passed'],verified
            rejected=q.decode(binary,secure+'/owned.mp4',3)
            assert rejected['first_frame_seconds']is None and any('certificate'in s.lower()for s in rejected['errors']),rejected
            (root/'nested.m3u8').write_text('#EXTM3U\n#EXT-X-TARGETDURATION:4\n#EXTINF:4,\n'+secure+'/owned.mp4\n#EXT-X-ENDLIST\n',encoding='utf-8')
            try:q.preflight(plain+'/nested.m3u8')
            except Exception as error:
                assert 'certificate'in str(error).lower(),type(error).__name__
            else:raise AssertionError('Invalid nested certificate was accepted')
            assert q.cover(binary,plain+'/cover.png')['ok'], 'Owned cover decode failed'
            assert not q.cover(binary,plain+'/missing.jpg')['ok']
            print('PASS: owned null audio/video, HTTP404, verified TLS, rejected TLS, nested rejected TLS, valid/invalid cover; no audio/display devices')
        finally:
            for instance in servers:instance.shutdown();instance.server_close()


if __name__=='__main__':main()
