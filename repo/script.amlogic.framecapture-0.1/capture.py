import ioctl
import fcntl
import time

CAP_FLAG_AT_CURRENT = 0
CAP_FLAG_AT_TIME_WINDOW = 1
CAP_FLAG_AT_END = 2

FMT_S24_RGB = ((1 << 24) | 0x00200) | (5 << 20)

AMVIDEOCAP_IOC_MAGIC = ord('V')
AMVIDEOCAP_IOW_SET_WANTFRAME_FORMAT = ioctl.IOW(AMVIDEOCAP_IOC_MAGIC, 0x01, 4)
AMVIDEOCAP_IOW_SET_WANTFRAME_WIDTH = ioctl.IOW(AMVIDEOCAP_IOC_MAGIC, 0x02, 4)
AMVIDEOCAP_IOW_SET_WANTFRAME_HEIGHT = ioctl.IOW(AMVIDEOCAP_IOC_MAGIC, 0x03, 4)
AMVIDEOCAP_IOW_SET_WANTFRAME_AT_FLAGS = ioctl.IOW(
    AMVIDEOCAP_IOC_MAGIC, 0x06, 4)

CAP_PATH = "/dev/amvideocap0"

# echo 1 > /sys/module/amvdec_h265/parameters/double_write_mode
# echo 1 > /sys/module/amvdec_vp9/parameters/double_write_mode


def capture_frame(width, height):

    buffersize = width * height * 3
    buffer = [0] * buffersize
    for i in xrange(3):
        print("Capturing frame " + str(i))
        fp = open(CAP_PATH, "rb")
        fcntl.ioctl(fp, AMVIDEOCAP_IOW_SET_WANTFRAME_FORMAT, FMT_S24_RGB)
        fcntl.ioctl(fp, AMVIDEOCAP_IOW_SET_WANTFRAME_WIDTH, width)
        fcntl.ioctl(fp, AMVIDEOCAP_IOW_SET_WANTFRAME_HEIGHT, height)
        fcntl.ioctl(fp, AMVIDEOCAP_IOW_SET_WANTFRAME_AT_FLAGS,
                    CAP_FLAG_AT_CURRENT)
        buffer = bytearray(fp.read(buffersize))
        fp.close()

    return buffer
