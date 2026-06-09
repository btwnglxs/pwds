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

parser.add_argument("--target", type=str, required=True, help="Host to scan [bright_black](for ex.: 192.168.0.1)[/]")
parser.add_argument("--wordlist", type=str, required=True, help="Directories wordlist [bright_black](for ex.: wordlist.txt)")
parser.add_argument("--threads", type=int, help="Scanning threads count [bright_black](default is 40, up to 80)[/]", default=40)
parser.add_argument("--depth", type=int, help="Maximum recursion depth [bright_black](default is 4)[/]", default=4)
parser.add_argument("--match_codes", type=str, help="List of match codes, separated by commas[bright_black](default is 200,301,302,401,403)[/]", default="200,301,302,401,403")

args = parser.parse_args()

valid_codes = [int(code.strip()) for code in args.match_codes.split(",")]

wordlist_queue = queue.Queue()
host = f"http://{args.target}"
founded_directories = []

state_lock = threading.Lock()
scanned_paths = set()
active_workers = 0

bad_size = None

wordlist = []

if args.threads > 100:
	THREADS = 100
else:
	THREADS = args.threads

try:
	with open(args.wordlist, "r") as f:
		for line in f:
			word = line.strip()
			if word:
				wordlist.append(word)
except FileNotFoundError:
	print(f"[bold red][!][/] File '{args.wordlist}' is not found.")
	sys.exit()
except PermissionError:
	print(f"[bold red][!][/] Permission error. Can't read file '{args.wordlist}'")
	sys.exit()

for word in wordlist:
	wordlist_queue.put((word, 0))

def banner():
	print(r"""[bold blue]
                    _
   _ ____      ____| |___
  | '_ \ \ /\ / / _` / __| [bold blue][bright_black]by[/] btwnglxs[/]
  | |_) \ V  V / (_| \__ \ [bright_black]ver-0.1[/]
  | .__/ \_/\_/ \__,_|___/ [bold white]Python Web Directory Scanner[/]
  |_|
[/]""")

	print("   --------------------------------------------------------------------")
	print("  ")
	print(f"   [bright_black]Target      [/]| [bold white]{host}[/]")
	print(f"   [bright_black]Wordlist    [/]| [bold white]{args.wordlist}[/]")
	print(f"   [bright_black]Threads     [/]| [bold white]{THREADS}[/]")
	print(f"   [bright_black]Depth       [/]| [bold white]{args.depth}[/]")
	print(f"   [bright_black]Match Codes [/]| [bold white]{args.match_codes}[/]")
	print("  ")
	print("   --------------------------------------------------------------------")
	print("\n")

def get_bad_size():

	global bad_size

	try:

		r = requests.get(f"{host}/1106451782365012783512783118644", timeout=5, allow_redirects=False)
		bad_size = int(r.headers.get('content-length', len(r.content)))

	except requests.exceptions.RequestException:
		bad_size = None

	except Exception as e:
		print(f"[bold red][!][/] Error: {e}")

def scan_dir(progress, task_id):
	global active_workers

	while True:
		try:
			directory, current_depth = wordlist_queue.get(timeout=0.1)
		except queue.Empty:
			with state_lock:
				if active_workers == 0:
					break
			continue

		url = f"{host}/{directory}"

		with state_lock:
			if url in scanned_paths:
				progress.advance(task_id, advance=1)
				continue
			scanned_paths.add(url)
			active_workers += 1

		try:
			headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

			r = requests.get(url, headers=headers, timeout=2, allow_redirects=False)

			length = r.headers.get('content-length')

			if r.status_code in valid_codes :
				if bad_size is None or length != bad_size:
					with state_lock:
						founded_directories.append((directory, r.status_code))

					progress.print(f"   [bold green][+][/] [bold white]/{directory}[/] [bright_black](Status: {r.status_code}, Depth: {current_depth}, CL: {length})[/]")

					if current_depth < args.depth:
						with state_lock:
							added_count = 0
							for word in wordlist:
								new_path = f"{directory}/{word}"
								new_url = f"{host}/{new_path}"
								if new_url not in scanned_paths:
									wordlist_queue.put((new_path, current_depth + 1))
									added_count += 1

							if added_count > 0:
								progress.update(task_id, total=progress.tasks[task_id].total + added_count)

		except requests.exceptions.RequestException:
			pass
		finally:
			with state_lock:
				active_workers -= 1
			progress.advance(task_id, advance=1)

def build_nested_dict(paths):
	root = {}
	for path, code in paths:
		parts = path.strip("/").split("/")
		current_level = root
		for i, part in enumerate(parts):
			if part not in current_level:
				current_level[part] = {}

			if i == len(parts) - 1:
				current_level[part]["_code"] = code

			current_level = current_level[part]
	return root

def add_nodes_to_rich_tree(rich_node, nested_dict):
	for key, value in sorted(nested_dict.items()):
		if key == "_code":
			continue

		code = value.get("_code", None)
		if code == 200:
			label = f"[bold green]{key}[/] [bright_black]({code})[/]"
		elif code in [301, 302]:
			label = f"[bold yellow]{key}[/] [bright_black]({code})[/]"
		elif code in [401, 403]:
			label = f"[bold red]{key}[/] [bright_black]({code})[/]"
		else:
			label = f"[white]{key}[/]"

		branch = rich_node.add(label, guide_style="bright_black")

		add_nodes_to_rich_tree(branch, value)


def main():

	banner()

	threads = []

	get_bad_size()

	try:
		with Progress() as progress:
			task = progress.add_task(f"   [bold white]Scanning...[/] ", total=len(wordlist))

			for i in range(THREADS):
				t = threading.Thread(target=scan_dir, args=(progress, task))
				t.daemon = True
				threads.append(t)
				t.start()

			for t in threads:
				t.join()

		print(f"\n   Scanning '[bold cyan]{host}[/]' is [bold green]complete[/].\n")

		if founded_directories:

			print(f"   [bold blue]📂 {host}[/]")

			sorted_directories = sorted(founded_directories, key=lambda x: x[0])

			for i, (path, code) in enumerate(sorted_directories):
				depth = path.count("/")

				is_last = (i == len(sorted_directories) - 1)
				icon = "╰" if is_last else "├"

				lines = "─" * (2 + depth * 4)

				name = path.split("/")[-1]

				if code == 200:
					label = f"[bold green]{name}[/] [bright_black]({code})[/]"
				elif code in [301, 302]:
					label = f"[bold yellow]{name}[/] [bright_black]({code})[/]"
				elif code in [401, 403]:
					label = f"[bold red]{name}[/] [bright_black]({code})[/]"
				else:
					label = f"[white]{name}[/]"

				print(f"   {icon}{lines} {label}")
		else:
			print("[bold red][!][/] No directories founded.")


	except KeyboardInterrupt:
		print("\n   [bold orange][!] Keyboard interrupt. Exiting...[/]")
		sys.exit()
	except Exception as e:
		print(f"   [bold red][!][/] Error : {e}")
		sys.exit()

if __name__ == "__main__":
	main()
