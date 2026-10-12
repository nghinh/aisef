"""Deterministic reproduction of the exact error, stdlib `io` only, no subprocess, no sleeps, no timing assertions.

The object is the stdin of ProcessRange's anchor: Popen(..., encoding='utf-8') makes it
TextIOWrapper(BufferedWriter(FileIO)). The raw below stands in for FileIO of a pipe whose reader has exited:
  write() -> BrokenPipeError (EPIPE: what release() meets when a second releaser writes EXIT after the anchor is gone)
  close() -> held until the test lets it go (the close(2) syscall, made as wide as the test needs)
  closed  -> reports to the test when thread X reads it (X has passed a CHECK_CLOSED)

Level 1  BufferedWriter: Y.close() is inside raw.close(); X.flush() has read raw.closed == False.
Level 2  TextIOWrapper(BufferedWriter): the shape of _close_pipes() run by two threads; X is released after its
         k-th read of raw.closed, k = 1..6, to show which ValueError each window gives.
"""
import io, sys, threading

class GatedRaw(io.RawIOBase):
    def __init__(self, x_reads=1):
        super().__init__()
        self.in_close = threading.Event()   # Y is inside raw.close()
        self.go = threading.Event()         # let raw.close() finish
        self.x_ident = None
        self.x_reads, self.x_seen = x_reads, 0
        self.x_checked = threading.Event()  # X has read raw.closed `x_reads` times
    def writable(self): return True
    def write(self, b): raise BrokenPipeError(32, "Broken pipe")
    @property
    def closed(self):
        value = io.RawIOBase.closed.__get__(self)
        if threading.get_ident() == self.x_ident:
            self.x_seen += 1
            if self.x_seen == self.x_reads:
                self.x_checked.set()
        return value
    def close(self):
        if not io.RawIOBase.closed.__get__(self):
            self.in_close.set()
            assert self.go.wait(20), "gate never released"
        super().close()

def level1():
    raw = GatedRaw(x_reads=1)
    w = io.BufferedWriter(raw)
    w.write(b"EXIT\n")                       # pending in the buffer: write_pos 0 < write_end 5
    out = {}
    def y():
        try: w.close()
        except BaseException as e: out["Y.close"] = e
    def x():
        raw.x_ident = threading.get_ident()
        try: w.flush()
        except BaseException as e: out["X.flush"] = e
    ty = threading.Thread(target=y); ty.start()
    assert raw.in_close.wait(20)             # Y: first flush failed (EPIPE), now inside raw.close() holding the lock
    tx = threading.Thread(target=x); tx.start()
    assert raw.x_checked.wait(20)            # X has passed `flush of closed file` (raw.closed was False)
    raw.go.set(); ty.join(); tx.join()
    return out

def level2(k):
    raw = GatedRaw(x_reads=k)
    tw = io.TextIOWrapper(io.BufferedWriter(raw), encoding="utf-8", write_through=True)
    tw.write("EXIT\n")                        # buffered by BufferedWriter
    try: tw.flush()
    except OSError: pass                      # the EPIPE release() ignores; the bytes stay pending
    out = {}
    def y():
        try: tw.close()
        except BaseException as e: out["Y.close"] = e
    def x():
        raw.x_ident = threading.get_ident()
        try: tw.close()
        except BaseException as e: out["X.close"] = e
    ty = threading.Thread(target=y); ty.start()
    assert raw.in_close.wait(20)
    tx = threading.Thread(target=x); tx.start()
    ok = raw.x_checked.wait(2.0)             # if X never reads closed k times it is already blocked: release anyway
    raw.go.set(); ty.join(); tx.join()
    return out, ok

if __name__ == "__main__":
    print(sys.version.split()[0])
    out = level1()
    print("level 1: Y.close ->", repr(out.get("Y.close")), "| X.flush ->", repr(out.get("X.flush")))
    for k in range(1, 7):
        out, reached = level2(k)
        print(f"level 2 k={k} (X's closed-read #{k} reached={reached}): Y.close -> {out.get('Y.close')!r} | X.close -> {out.get('X.close')!r}")

# ---------------------------------------------------------------------------------------------- level 3: H1
class GatedReader(io.RawIOBase):
    """the stdout side: TextIOWrapper(BufferedReader(raw)); readinto() gives one line then EOF; close() is gated"""
    def __init__(self, x_reads):
        super().__init__()
        self.in_close, self.go, self.x_checked = threading.Event(), threading.Event(), threading.Event()
        self.x_ident, self.x_reads, self.x_seen, self._sent = None, x_reads, 0, False
    def readable(self): return True
    def readinto(self, b):
        if self._sent:
            return 0
        self._sent = True
        data = b"line\n"
        b[:len(data)] = data
        return len(data)
    @property
    def closed(self):
        value = io.RawIOBase.closed.__get__(self)
        if threading.get_ident() == self.x_ident:
            self.x_seen += 1
            if self.x_seen == self.x_reads:
                self.x_checked.set()
        return value
    def close(self):
        if not io.RawIOBase.closed.__get__(self):
            self.in_close.set()
            assert self.go.wait(20)
        super().close()

def level3(k):
    """X = the pump thread asking for the next line (here the stream is at its end); Y = main closing stdout."""
    raw = GatedReader(x_reads=k)
    tw = io.TextIOWrapper(io.BufferedReader(raw), encoding="utf-8")
    assert next(tw) == "line\n"
    out = {}
    def y():
        try: tw.close()
        except BaseException as e: out["Y(main).close"] = e
    def x():
        raw.x_ident = threading.get_ident()
        try: next(tw)
        except StopIteration: out["X(pump).next"] = "StopIteration"
        except BaseException as e: out["X(pump).next"] = e
    ty = threading.Thread(target=y); ty.start()
    assert raw.in_close.wait(20)
    tx = threading.Thread(target=x); tx.start()
    ok = raw.x_checked.wait(2.0)
    raw.go.set(); ty.join(); tx.join()
    return out, ok

if __name__ == "__main__":
    print("-- level 3 (H1: reader thread vs close on stdout)")
    for k in range(1, 5):
        out, reached = level3(k)
        print(f"level 3 k={k} reached={reached}: main close -> {out.get('Y(main).close')!r} | pump next -> {out.get('X(pump).next')!r}")
