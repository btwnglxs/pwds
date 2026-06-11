import requests
import threading
import time
import argparse
from rich_argparse import RichHelpFormatter
from rich.progress import Progress
from rich.padding import Padding
from rich.tree import Tree
from rich import print
from rich.console import Console
import sys
import queue

RichHelpFormatter.text_markup = True
RichHelpFormatter.help_markup = True

parser = argparse.ArgumentParser(
    description="[bold white]Python Web Directory Scanner[/] [bright_black]by[/] [bold blue]btwnglxs[/]",
    formatter_class=RichHelpFormatter,
    epilog="[bright_black]EXAMPLE : python dir_scanner.py --host 192.168.0.1 --wordlist wordlist.txt --depth 2[/]"
)

parser.add_argument("--target",      type=str, required=True, help="Host to scan [bright_black](for ex.: 192.168.0.1)[/]")
parser.add_argument("--wordlist",    type=str, required=True, help="Directories wordlist [bright_black](for ex.: wordlist.txt)")
parser.add_argument("--threads",     type=int, help="Scanning threads count [bright_black](default is 40, up to 100)[/]", default=40)
parser.add_argument("--depth",        type=int, help="Maximum recursion depth [bright_black](default is 4)[/]", default=4)
parser.add_argument("--match_codes",  type=str, help="List of match codes, separated by commas[bright_black](default is 200,301,302,401,403)[/]", default="200,301,302,401,403")

args = parser.parse_args()

valid_codes = [int(code.strip()) for code in args.match_codes.split(",")]

wordlist_queue = queue.Queue()
host = f"http://{args.target}" if not args.target.startswith(("http://", "https://")) else args.target
founded_directories = []

scanned_lock  = threading.Lock()
results_lock  = threading.Lock()
progress_lock = threading.Lock()

scanned_paths = set()
bad_size      = None
wordlist      = []

THREADS = min(args.threads, 100)

try:
    with open(args.wordlist, "r") as f:
        for line in f:
            word = line.strip()
            if word and not word.startswith("#"):
                wordlist.append(word)
except FileNotFoundError:
    print(f"[bold red][!][/] File '{args.wordlist}' is not found.")
    sys.exit()
except PermissionError:
    print(f"[bold red][!][/] Permission error. Can't read file '{args.wordlist}'")
    sys.exit()

wordlist_queue.put(("", 0))


def banner():

    print(r"""[bold blue]
                    _
   _ ____      ____| |___
  | '_ \ \ /\ / / _` / __| [bold blue][bright_black]by[/] [link=https://github.com]btwnglxs[/link][/]
  | |_) \ V  V / (_| \__ \ [bright_black]ver-0.1.1[/]
  | .__/ \_/\_/ \__,_|___/ [bold white]Python Web Directory Scanner[/]
  |_|
[/]""")

    print("   [bright_black]--------------------------------------------------------------------[/]")
    print("  ")
    print(f"   [bold white]Target      [/]  [bright_black]{host}[/]")
    print(f"   [bold white]Wordlist    [/]  [bright_black]{args.wordlist}[/]")
    print(f"   [bold white]Threads     [/]  [bright_black]{THREADS} / 100[/]")
    print(f"   [bold white]Depth       [/]  [bright_black]{args.depth} / ANY[/]")
    print(f"   [bold white]Match Codes [/]  [bright_black]{args.match_codes}[/]")
    print("  ")
    print("   [bright_black]--------------------------------------------------------------------[/]")
    print("\n")


def get_bad_size():

    global bad_size

    try:
        with requests.get(f"{host}/1106451782365012783512783118644", timeout=(5, 5), allow_redirects=False, stream=True) as r:
            bad_size = int(r.headers.get("content-length", 0))

    except requests.exceptions.RequestException:
        bad_size = None

    except Exception as e:
        print(f"[bold red][!][/] Error: {e}")
        sys.exit()


def scan_dir(progress, task_id):

    session = requests.Session()
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

    while True:
        task = wordlist_queue.get()

        if task is None:
            wordlist_queue.task_done()
            break

        base_directory, current_depth = task

        try:
            for word in wordlist:

                directory = (f"{base_directory}/{word}" if base_directory else word)

                with scanned_lock:
                    if directory in scanned_paths:
                        with progress_lock:
                            progress.advance(task_id)
                        continue

                    scanned_paths.add(directory)

                url = f"{host}/{directory}"

                try:
                    with session.get(url, headers=headers, timeout=(2, 2), allow_redirects=False, stream=True) as r:
                        length = int(r.headers.get("content-length", 0))

                        if (r.status_code in valid_codes and (bad_size is None or length != bad_size)):
                            with results_lock:
                                founded_directories.append((directory, r.status_code))

                            with progress_lock:
                                progress.print(f"   [bold green][+][/] "f"[bold white]/{directory}[/] [bright_black]({r.status_code}, Depth: {current_depth}, CL: {length})[/]")

                            if (r.status_code in (301, 302) and current_depth < args.depth):
                                wordlist_queue.put((directory, current_depth + 1))

                                with progress_lock:
                                    progress.update(task_id, total=(progress.tasks[task_id].total + len(wordlist)))

                except requests.exceptions.RequestException:
                    pass

                finally:
                    with progress_lock:
                        progress.advance(task_id)

        finally:
            wordlist_queue.task_done()

    session.close()


def main():

    banner()
    threads = []
    get_bad_size()

    try:
        with Progress() as progress:
            task = progress.add_task("[bold white]   Scanning...[/]", total=len(wordlist))

            for _ in range(THREADS):
                t = threading.Thread(target=scan_dir, args=(progress, task), daemon=True)
                threads.append(t)
                t.start()

            wordlist_queue.join()

            for _ in range(THREADS):
                wordlist_queue.put(None)

            for t in threads:
                t.join()

        print("\n   [bright_black]--------------------------------------------------------------------[/]")

        print(f"\n   Scanning '[bold cyan]{host}[/]' is [bold green]complete[/].\n")

        if founded_directories:
            print(f"   [bold white]📂 {args.target}[/]")
            sorted_directories = sorted(founded_directories, key=lambda x: x[0])

            for i, (path, code) in enumerate(sorted_directories):
                depth   = path.count("/")
                is_last = (i == len(sorted_directories) - 1)
                icon    = "╰" if is_last else "├"
                lines   = "─" * (2 + depth * 4)
                name    = path.split("/")[-1]

                if code == 200:
                    label = f"[bold green]{name}[/] [bright_black]{code}[/]"
                elif code in [301, 302]:
                    label = f"[bold yellow]{name}[/] [bright_black]{code}[/]"
                elif code in [401, 403]:
                    label = f"[bold red]{name}[/] [bright_black]{code}[/]"
                else:
                    label = f"[white]{name}[/] [bright_black]{code}[/]"

                print(f"   {icon}{lines} {label}")

        else:
            print("[bold red]   [!][/] No directories founded.")

    except KeyboardInterrupt:
        print("\n[bold yellow]   [!] Keyboard interrupt. Quitting...[/]")
        sys.exit()
    except Exception as e:
        print(f"   [bold red][!][/] Error : {e}")
        sys.exit()


if __name__ == "__main__":
    main()
