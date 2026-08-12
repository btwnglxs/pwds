import urllib3
import requests
import threading
import time
import argparse
from rich.progress import Progress, TextColumn, BarColumn, TaskProgressColumn, TimeRemainingColumn
from rich.padding import Padding
from rich.tree import Tree
from rich import print
from rich.console import Console
import sys
import queue

pwds_version = "0.3.0"

console = Console(record=True)

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

#TODO - добавить auto-filter wildcard domains
#TODO - добавить счётчик запросов в секунду
#TODO - добавить `--json`, default: False
#TODO - добавить `--html`, default: False
#TODO - добавить `--output`, default: stdout
#TODO - добавить `--rate-limit`, default: None

parser = argparse.ArgumentParser(description="Python Web Directory Scanner by btwnglxs", epilog="EXAMPLE : ./pwds --host 192.168.0.1 --wordlist wordlist.txt --threads 10 --depth 7 --match_codes 200,301,302,401,427,403,501 --extensions .bak,~,.tar,.tar.xz.,gz.,.tar.gz --user-agent \"Mozilla/5.0 (Windows NT 10.0; Win64; x64)\" --timeout 3 --proxy http://127.0.0.1:8080")

parser.add_argument("--target","-t", type=str, required=True, help="Host to scan (for ex.: 192.168.0.1)")
parser.add_argument("--wordlist","-w", type=str, required=True, help="Directories wordlist (for ex.: wordlist.txt)")
parser.add_argument("--threads", type=int, help="Scanning threads count (default: 40)", default=40)
parser.add_argument("--depth", type=int, help="Maximum recursion depth (default: 4)[/]", default=4)
parser.add_argument("--match_codes", type=str, help="List of match codes, separated by commas(default: 200,301,302,401,403)", default="200,301,302,401,403")
parser.add_argument("--extensions","-e", type=str, help="List of extensions to add to any search word(default: None)")
parser.add_argument("--user-agent", type=str, help=f"User-Agent for scanning (default: pwds/{pwds_version})", default=f"pwds/{pwds_version}")
parser.add_argument("--timeout", type=int, help="Timeout for requests (default: 2)", default=2)
parser.add_argument("--proxy", type=str, help="Proxy for scanning (default: None)")
parser.add_argument("--no-recursion", action='store_true', help="Disables recursion (default: False)")

args = parser.parse_args()

valid_codes = [int(code.strip()) for code in args.match_codes.split(",")]

valid_extensions = [extension.strip().lstrip(".") for extension in args.extensions.split(",") if extension.strip()] if args.extensions else []

wordlist_queue = queue.Queue(maxsize=100000)
host = f"http://{args.target}" if not args.target.startswith(("http://", "https://")) else args.target
found_directories = []

scanned_lock  = threading.Lock()
results_lock  = threading.Lock()

scanned_paths = set()
bad_size      = None
bad_size_ht   = None
wordlist      = []

if args.proxy:
	THREADS = min(args.threads, 10)
else:
	THREADS = min(args.threads, 100)

if args.no_recursion:
	args.depth = 0

args.timeout = max(args.timeout, 1)

progress_bar = BarColumn(style="underline bold black", complete_style="underline bold blue", finished_style="underline bold green")

try:
	with open(args.wordlist, "r") as f:
		for line in f:
			word = line.strip().rstrip("/")
			if word and not word.startswith("#"):
				wordlist.append(word)

except FileNotFoundError:
	print(f"\n  [bold red][!][/] File '{args.wordlist}' is not found.")
	sys.exit(1)

except PermissionError:
	print(f"\n  [bold red][!][/] Permission error. Can't read file '{args.wordlist}'")
	sys.exit(1)

except UnicodeDecodeError:
	print(f"\n  [bold red][!][/] Unicode decode error. File '{args.wordlist}' is not readable as wordlist.")
	sys.exit(1)

wordlist = list(set(wordlist))

words_per_dir = len(wordlist) * (len(valid_extensions) + 1) if valid_extensions else len(wordlist)

def banner():

	print(rf"""[bold blue]
		    _
   _ ____      ____| |___
  | '_ \ \ /\ / / _` / __| [bold white]Python Web Directory Scanner[/]
  | |_) \ V  V / (_| \__ \ [bold blue][bright_black]by[/] [link=https://github.com/btwnglxs]btwnglxs[/link][/]
  | .__/ \_/\_/ \__,_|___/ [bright_black]ver-{pwds_version}[/]
  |_|
[/]""")

	print("   [bright_black]─────────────────────────────────────────────────────────────────[/]")
	print("  ")
	print(f"   [bold white]Target      [/]  [bright_black]{host}[/]")
	print(f"   [bold white]Wordlist    [/]  [bright_black]{args.wordlist}[/]")
	print(f"   [bold white]User-Agent  [/]  [bright_black]{args.user_agent}[/]")
	print(f"   [bold white]Threads     [/]  [bright_black]{THREADS} / 100[/]")
	print(f"   [bold white]Depth       [/]  [bright_black]{args.depth if args.depth > 1 else "non-recursive"} / ANY[/]")
	print(f"   [bold white]Match Codes [/]  [bright_black]{args.match_codes}[/]")
	print(f"   [bold white]Timeout     [/]  [bright_black]{args.timeout}[/]")
	print(f"   [bold white]Extensions  [/]  [bright_black]{args.extensions if args.extensions else '-'}[/]")
	print(f"   [bold white]Proxy       [/]  [bright_black]{args.proxy if args.proxy else '-'}[/]")
	print("  ")
	print("   [bright_black]─────────────────────────────────────────────────────────────────[/]")
	#print("\n")

def get_bad_size():

	global bad_size
	global bad_words
	global bad_lines

	global bad_size_ht
	global bad_words_ht
	global bad_lines_ht

	if args.proxy:
		if args.proxy.startswith(("http://","https://")):
			proxies = {"http": args.proxy, "https": args.proxy}
		else:
			proxy = f"http://{args.proxy}"
			proxies = {"http": proxy, "https": proxy}

	try:

		if args.proxy:
			with requests.get(f"{host}/1106451782365012783512783118644", timeout=(5, 5), allow_redirects=False, proxies=proxies) as r:
				bad_size = int(r.headers.get("content-length", len(r.content)))
				bad_page_text = r.text
				bad_lines = len(bad_page_text.splitlines())
				bad_words = len(bad_page_text.split())

		else:
			with requests.get(f"{host}/1106451782365012783512783118644", timeout=(5, 5), allow_redirects=False) as r:
				bad_size = int(r.headers.get("content-length", len(r.content)))
				bad_page_text = r.text
				bad_lines = len(bad_page_text.splitlines())
				bad_words = len(bad_page_text.split())

	except (requests.exceptions.ProxyError, requests.exceptions.ConnectionError):
		print(f"\n  [bold red][!][/] Proxy Error: Connection broken during calibration.")
		sys.exit(1)

	except requests.exceptions.RequestException:
		bad_size = None
		bad_lines = None
		bad_words = None

	except Exception as e:
		print(f"\n  [bold red][!][/] Error: {e}")
		sys.exit(1)

	try:

		if args.proxy:
			with requests.get(f"{host}/.ht0912837465160348189031340", timeout=(5, 5), allow_redirects=False, proxies=proxies) as r:
				bad_size_ht = int(r.headers.get("content-length", len(r.content)))
				bad_page_text_ht = r.text
				bad_lines_ht = len(bad_page_text_ht.splitlines())
				bad_words_ht = len(bad_page_text_ht.split())

		else:
			with requests.get(f"{host}/.ht0912837465160348189031340", timeout=(5, 5), allow_redirects=False) as r:
				bad_size_ht = int(r.headers.get("content-length", len(r.content)))
				bad_page_text_ht = r.text
				bad_lines_ht = len(bad_page_text_ht.splitlines())
				bad_words_ht = len(bad_page_text_ht.split())

	except (requests.exceptions.ProxyError, requests.exceptions.ConnectionError):
		print(f"\n  [bold red][!][/] Proxy Error: Connection broken during calibration.")
		sys.exit(1)

	except requests.exceptions.RequestException:
		bad_size_ht = None
		bad_words_ht = None
		bad_lines_ht = None

	except Exception as e:
		print(f"\n  [bold red][!][/] Error: {e}")
		sys.exit(1)

def scan_dir(progress, task_id):

	session = requests.Session()
	headers = {"User-Agent": args.user_agent}

	adapter = requests.adapters.HTTPAdapter(pool_connections=THREADS, pool_maxsize=THREADS)
	session.mount("http://", adapter)
	session.mount("https://", adapter)

	if args.proxy:
		if args.proxy.startswith(("http://","https://")):
			session.proxies = {"http": args.proxy, "https": args.proxy}
		else:
			proxy = f"http://{args.proxy}"
			session.proxies = {"http": proxy, "https": proxy}

	while True:
		task = wordlist_queue.get()

		if task is None:
			wordlist_queue.task_done()
			break

		base_directory, current_depth = task

		try:
			for word in wordlist:

				words_to_check = [word] + [f"{word}.{extension}" for extension in valid_extensions] if valid_extensions else [word]

				for current_word in words_to_check:

					directory = (f"{base_directory}/{current_word}" if base_directory else current_word)

					with scanned_lock:
						if directory in scanned_paths:
							progress.advance(task_id)
							continue

						scanned_paths.add(directory)

					url = f"{host}/{directory}"

					try:
						with session.get(url, headers=headers, timeout=(args.timeout, args.timeout), allow_redirects=False, stream=True, verify=False) as r:
							length = int(r.headers.get("content-length", 0))

							if (r.status_code in valid_codes and (bad_size is None or length != bad_size) and (bad_size_ht is None or length != bad_size_ht) and not (r.status_code in (301, 302) and length == 0) and not (r.status_code == 200 and length == 0)):
								with results_lock:
									found_directories.append((directory, r.status_code))

								progress.print(f"   [bold green][+][/] "f"[bold white]/{directory}[/] [bright_black]({r.status_code}, Depth: {current_depth}, CL: {length})[/]")

								if (r.status_code in (301, 302) and current_depth < args.depth):
									wordlist_queue.put((directory, current_depth + 1))

									progress.update(task_id, total=(progress.tasks[task_id].total + words_per_dir))

					except requests.exceptions.RequestException:
						pass

					finally:
							progress.advance(task_id)

		finally:
			wordlist_queue.task_done()

	session.close()

def main():

	banner()
	threads = []
	get_bad_size()

	try:
		with Progress(TextColumn("{task.description}"), progress_bar, TaskProgressColumn(), TimeRemainingColumn(), transient=True) as progress:
			task = progress.add_task("[bold white]   Scanning...[/]", total=words_per_dir)

			wordlist_queue.put(("", 0))

			for _ in range(THREADS):
				t = threading.Thread(target=scan_dir, args=(progress, task), daemon=True)
				threads.append(t)
				t.start()

			wordlist_queue.join()

			for _ in range(THREADS):
				wordlist_queue.put(None)

			for t in threads:
				t.join()

		print("   [bright_black]─────────────────────────────────────────────────────────────────[/]")

		print(f"\n   Scanning '[bold cyan]{host}[/]' is [bold green]complete[/].\n")

		if found_directories:
			print(f"   [bold white]📂 {args.target}[/]")
			sorted_directories = sorted(found_directories, key=lambda x: x[0])

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
			print("[bold red]   [!][/] No directories found.")

	except KeyboardInterrupt:
		print("\n[bold yellow]   [!] KeyboardInterrupt. Quitting...[/]")

		print("\n   [bright_black]─────────────────────────────────────────────────────────────────[/]")

		print(f"\n   Scanning '[bold cyan]{host}[/]' was [bold yellow]interrupted[/].\n")

		if found_directories:
			print(f"   [bold white]📂 {args.target}[/]")
			sorted_directories = sorted(found_directories, key=lambda x: x[0])

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
			print("[bold red]   [!][/] No directories found.")
		sys.exit()

	except Exception as e:
		print(f"   \n  [bold red][!][/] Error : {e}")
		sys.exit(1)

if __name__ == "__main__":
	main()
