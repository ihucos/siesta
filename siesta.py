#!/usr/bin/env python3
import os
import shlex
import io
import sys
import subprocess
from uuid import uuid4
import hashlib
import json
import re
import shelve
from litellm import completion
from concurrent.futures import ThreadPoolExecutor

from jinja2 import Environment, FileSystemLoader
from jinja2.exceptions import TemplateNotFound


class Siesta:
    def __init__(self, argv):
        self.argv = argv
        self.template_file = argv[1]
        self._uuid2futures = {}
        self.env = Environment(
            loader=FileSystemLoader(os.path.dirname(self.template_file)),
            lstrip_blocks=True,
        )

    def run(self):
        self.pool = ThreadPoolExecutor()
        self.cache = shelve.open(os.path.expanduser("~/.prompt_cache"))
        template = self.env.get_template(os.path.basename(self.template_file))
        output = template.render(argv=sys.argv, input=" ".join(sys.argv[2:]))

        lines = output.splitlines()
        if lines and lines[0].startswith("#!"):
            lines = lines[1:]
        print("\n".join(lines).strip("\n"))

    def filter(self, func):
        name = func.__name__.rstrip("_")
        self.env.filters[name] = lambda *args, **kwargs: self._expand_futures(
            func(*args, **kwargs)
        )
        return func

    def _expand_futures(self, stri):
        for uuid, future in self._uuid2futures.items():
            if uuid in stri:
                stri = stri.replace(uuid, future.result())
        return stri

    def register_future(self, future):
        uuid = str(uuid4())
        self._uuid2futures[uuid] = future
        return uuid


try:
    siesta = Siesta(sys.argv)
except IndexError:
    print("usage: siesta <template-file> <args>")
    sys.exit(1)


@siesta.filter
def run(input, cmd="bash", label=False, silentfail=False):
    # Start the process
    if not isinstance(cmd, str):
        cmd = shlex.join(cmd)

    input = input.strip(" \n")

    process = subprocess.Popen(
        cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, shell=True, text=True
    )

    # Send input and capture output
    stdout, _ = process.communicate(input=input)

    # Print the results
    if process.returncode != 0:
        if silentfail:
            return ""
        print(f"Error calling subprocess: {cmd}")
        sys.exit(1)

    if label:
        return f"```{cmd}\n$ {input}\n{stdout}\n\n```"

    return stdout


@siesta.filter
def debug(input):
    print(input)
    print("=== DEBUG DIE DIE ===")
    sys.exit(0)


def prompt_sync(prompt, model, **kwargs):
    # Import on-demand because its slow

    cache_key = hashlib.sha256(f"{model}:{prompt}:{kwargs}".encode()).hexdigest()
    if os.environ.get("SIESTA_CACHE") in ("yes", "true", "1"):
        cached = None
    else:
        cached = siesta.cache.get(cache_key)
    if cached is not None:
        return cached
    else:
        response = completion(
            model=model,
            messages=[{"content": prompt, "role": "user"}],
            stream=True,
            **kwargs,
        )
        msg = io.StringIO()
        for chunk in response:
            delta = chunk.choices[0].delta.content
            if not delta:
                break
            msg.write(delta)
            if os.environ.get("SIESTA_VERBOSE") in ("yes", "true", "1"):
                sys.stderr.write(delta)
                sys.stderr.flush()

        msgval = msg.getvalue()
        siesta.cache[cache_key] = msgval

        return msgval


@siesta.filter
def prompt(model, input, **kwargs):
    future = siesta.pool.submit(prompt_sync, model, input, **kwargs)
    return siesta.register_future(future)


@siesta.filter
def read(file):
    with open(file) as f:
        return f.read()
    return ""


@siesta.filter
def write(content, file):
    with open(file, "w") as f:
        f.write(content)
    return ""


@siesta.filter
def append(content, file):
    with open(file, "a") as f:
        f.write(content)
    return ""


@siesta.filter
def catfiles(app, inp):
    files = re.findall(r"(\w+\/[\w/\.]+)", inp)  # BUGGED, rewrite re
    contents = io.StringIO()
    for file in files:
        if os.path.exists(file):
            with open(file, "r") as f:
                content = f.read()
                contents.write(f"=== file: {file} ===\n{content}\n======\n")
    return contents.getvalue()


@siesta.filter
def code(inp):
    triple_quotes = re.findall(r"```(.*?)```", inp, re.DOTALL)
    single_quotes = re.findall(r"`(.*?)`", inp, re.DOTALL)
    if triple_quotes:
        return "\n".join(triple_quotes[-1].splitlines()[1:])
    if single_quotes:
        return single_quotes[-1]
    return inp


@siesta.filter
def askrun(inp):
    print(f"$ {inp}")
    try:
        ask = input("[R]epeat, E[x]ecute, E[d] or [Q]uit?")
    except KeyboardInterrupt:
        print()
        sys.exit(130)
    if ask == "":
        ask = "r"

    if ask == "x":
        os.execlp("bash", "bash", "-c", inp)
    elif ask == "r":
        siesta.run()
    elif ask == "q":
        sys.exit(0)
    return ""


@siesta.filter
def quote(stri):
    return shlex.quote(stri)


@siesta.filter
def print_(stri):
    print(stri)
    return stri


@siesta.filter
def json_(stri):
    return json.loads(stri)


@siesta.filter
def askedit(stri):
    result = subprocess.run(
        ["dialog", "--inputbox", "Edit", "10", "100", stri],  # Example command
        text=True,  # Handle output as text (str)
        stderr=subprocess.PIPE,  # Capture only stderr
        check=True,  # Raise an exception on s;
    )
    return result.stderr


def main():
    siesta.run()


if __name__ == "__main__":
    main()
