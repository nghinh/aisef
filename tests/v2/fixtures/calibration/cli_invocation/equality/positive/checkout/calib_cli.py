import sys

if __name__ == "__main__":
    sys.stdout.buffer.write((" ".join(sys.argv[1:]) + " ok\n").encode())
