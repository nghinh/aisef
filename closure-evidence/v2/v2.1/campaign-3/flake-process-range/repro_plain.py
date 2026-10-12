"""Stand-alone reproduction on a plain subprocess pair of pipes (no aisef2 import): the exact tail of
ProcessRange.release()/_close_pipes run by TWO threads on one Popen opened as ProcessRange.start() opens it
(stdin=PIPE, stdout=PIPE, encoding='utf-8', a pump thread iterating stdout).

usage: repro_plain.py <experiment> <iterations> [seed]
  two_release : two threads run the release tail (write EXIT/flush if poll() is None; wait; join pumper; close both pipes)
  one_release : the same tail, ONE thread only (the control: how often does the single-thread tail raise?)
  reader_close: H1 - the pump thread is inside `for line in stdout` while the main thread closes stdout (no join)
  two_close   : two threads only close stdin and stdout (no write)
"""
import collections, random, subprocess, sys, threading, time, faulthandler, traceback
faulthandler.dump_traceback_later(900, exit=True)
exp, n = sys.argv[1], int(sys.argv[2])
rnd = random.Random(int(sys.argv[3]) if len(sys.argv) > 3 else 1)
C = collections.Counter()
EX = {}   # first full traceback per distinct outcome

def note(where, e):
    key = f"{where}: {type(e).__name__}: {e}"
    C[key] += 1
    EX.setdefault(key, "".join(traceback.format_exception(e)))

def spawn(argv):
    p = subprocess.Popen(argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                         encoding="utf-8")
    def pump():
        try:
            for line in p.stdout:
                pass
        except BaseException as e:
            note("pump-thread", e)
    t = threading.Thread(target=pump, daemon=True)
    t.start()
    return p, t

def tail(p, pumper, tag, delay):
    time.sleep(delay) if delay else None
    try:
        if p.poll() is None:
            try:
                p.stdin.write("EXIT\n")
                p.stdin.flush()
            except OSError:
                pass
        p.wait()
        pumper.join(5.0)
        for name, pipe in (("stdin", p.stdin), ("stdout", p.stdout)):
            try:
                pipe.close()
            except OSError:
                pass
            except BaseException as e:
                note(f"{tag}.close({name})", e)
                raise
    except OSError as e:
        note(f"{tag}.tail", e)
    except BaseException:
        pass

def run_two():
    p, pumper = spawn(["head", "-n", "1"])
    bar = threading.Barrier(2)
    ds = [0, 0, 20e-6, 50e-6, 100e-6, 200e-6, 500e-6, 1e-3, 3e-3, 10e-3]
    da, db = rnd.choice(ds), rnd.choice(ds)
    def go(tag, d):
        bar.wait(); tail(p, pumper, tag, d)
    a = threading.Thread(target=go, args=("A", da)); b = threading.Thread(target=go, args=("B", db))
    a.start(); b.start(); a.join(); b.join()

def run_one():
    p, pumper = spawn(["head", "-n", "1"])
    tail(p, pumper, "A", 0)

def run_two_close():
    p, pumper = spawn(["head", "-n", "1"])
    p.stdin.write("EXIT\n"); p.stdin.flush(); p.wait(); pumper.join(5.0)
    bar = threading.Barrier(2)
    def go(tag):
        bar.wait()
        for name, pipe in (("stdin", p.stdin), ("stdout", p.stdout)):
            try:
                pipe.close()
            except OSError:
                pass
            except BaseException as e:
                note(f"{tag}.close({name})", e)
    a = threading.Thread(target=go, args=("A",)); b = threading.Thread(target=go, args=("B",))
    a.start(); b.start(); a.join(); b.join()

def run_reader_close():
    p = subprocess.Popen(["yes"], stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, encoding="utf-8")
    got = []
    def pump():
        try:
            for line in p.stdout:
                got.append(1)
        except BaseException as e:
            note("pump-thread", e)
    t = threading.Thread(target=pump, daemon=True); t.start()
    time.sleep(rnd.choice([0, 0.0002, 0.001, 0.003, 0.01]))
    done = threading.Event()
    def closer():
        try:
            p.stdout.close()
        except BaseException as e:
            note("main.close(stdout)", e)
        done.set()
    c = threading.Thread(target=closer, daemon=True); c.start()
    if not done.wait(3.0):
        C["close(stdout) still blocked after 3s"] += 1
    p.kill(); p.wait(); t.join(5.0)
    done.wait(3.0)
    if t.is_alive(): C["pump thread still alive"] += 1

def run_reader_blocked():
    """H1, the shape the lead named: the pump thread is BLOCKED in read() on stdout (the child holds it open and says
    nothing) when the main thread closes stdout. Does close() raise? In which thread does what land?"""
    p = subprocess.Popen(["sleep", "30"], stdin=subprocess.PIPE, stdout=subprocess.PIPE, encoding="utf-8")
    t = threading.Thread(target=lambda: _pump(p), daemon=True); t.start()
    time.sleep(0.02)                       # the pump is inside read()
    done = threading.Event()
    def closer():
        try:
            p.stdout.close()
            C["main close(stdout) returned normally"] += 1
        except BaseException as e:
            note("main.close(stdout)", e)
        done.set()
    c = threading.Thread(target=closer, daemon=True); c.start()
    if not done.wait(1.0):
        C["main close(stdout) BLOCKED >1s while the pump is in read()"] += 1
    p.kill(); p.wait()
    done.wait(5.0)
    t.join(5.0)
    if not done.is_set(): C["main close(stdout) never returned"] += 1

def _pump(p):
    try:
        for line in p.stdout:
            pass
        C["pump thread ended by plain EOF"] += 1
    except BaseException as e:
        note("pump-thread", e)

def run_two_close_pending():
    """The minimal natural one: the child has exited, so each thread's EXIT write meets EPIPE and its bytes stay
    pending in the BufferedWriter; both threads then close stdin and stdout at the same moment (a barrier)."""
    p = subprocess.Popen(["true"], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                         encoding="utf-8")
    p.wait()
    try:
        p.stdin.write("EXIT\n"); p.stdin.flush()      # EPIPE: ignored as release() ignores it; bytes stay pending
    except OSError:
        pass
    bar = threading.Barrier(2)
    def go(tag):
        bar.wait()
        for name, pipe in (("stdin", p.stdin), ("stdout", p.stdout)):
            try:
                pipe.close()
            except OSError:
                C["OSError (what _close_pipes ignores)"] += 1
            except BaseException as e:
                note(f"{tag}.close({name})", e)
    a = threading.Thread(target=go, args=("A",)); b = threading.Thread(target=go, args=("B",))
    a.start(); b.start(); a.join(); b.join()

def _two_close(pending, threads):
    p = subprocess.Popen(["true"], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                         encoding="utf-8")
    p.wait()
    if pending:
        try:
            p.stdin.write("EXIT\n"); p.stdin.flush()
        except OSError:
            pass
    bar = threading.Barrier(threads)
    def go(tag):
        bar.wait()
        for name, pipe in (("stdin", p.stdin), ("stdout", p.stdout)):
            try:
                pipe.close()
            except OSError:
                C["OSError (what _close_pipes ignores)"] += 1
            except BaseException as e:
                note(f"{tag}.close({name})", e)
    ts = [threading.Thread(target=go, args=(chr(65 + i),)) for i in range(threads)]
    for t in ts: t.start()
    for t in ts: t.join()

fn = {"two_close_no_pending": lambda: _two_close(False, 2), "one_close_pending": lambda: _two_close(True, 1),
      "three_close_pending": lambda: _two_close(True, 3), "two_close_pending": run_two_close_pending, "reader_blocked": run_reader_blocked, "two_release": run_two, "one_release": run_one, "reader_close": run_reader_close, "two_close": run_two_close}[exp]
t0 = time.time()
for i in range(n):
    fn()
print(f"experiment={exp} iterations={n} seconds={time.time()-t0:.1f}")
for k, v in sorted(C.items(), key=lambda kv: -kv[1]):
    print(f"{v:6d}  {k}")
if not C: print("     0  (no exception of any kind in any thread)")
if "-v" in sys.argv:
    for k, tb in EX.items(): print("----", k); print(tb)
