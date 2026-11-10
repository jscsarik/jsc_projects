"""Generate Windows multi-resolution ICO from the user's unmodified PNG."""
from pathlib import Path
import struct,sys
from PySide6.QtCore import QByteArray,QBuffer,QIODevice,Qt
from PySide6.QtGui import QImage
ROOT=Path(__file__).resolve().parents[1]

def make_icon(root=ROOT):
    image=QImage(str(root/'assets/title/logo.png'))
    if image.isNull():raise ValueError('assets/title/logo.png could not be loaded')
    frames=[]
    for size in (16,24,32,48,64,128,256):
        data=QByteArray();buffer=QBuffer(data);buffer.open(QIODevice.OpenModeFlag.WriteOnly)
        if not image.scaled(size,size,Qt.AspectRatioMode.KeepAspectRatio,Qt.TransformationMode.SmoothTransformation).save(buffer,'PNG'):raise RuntimeError('Icon PNG encoding failed')
        frames.append((size,bytes(data)))
    offset=6+16*len(frames);header=bytearray(struct.pack('<HHH',0,1,len(frames)))
    for size,data in frames:
        header.extend(struct.pack('<BBBBHHII',size if size<256 else 0,size if size<256 else 0,0,0,1,32,len(data),offset));offset+=len(data)
    path=root/'assets/title/logo.ico';path.write_bytes(bytes(header)+b''.join(data for size,data in frames));return path
if __name__=='__main__':print(make_icon())
