#!/usr/bin/env python3
import os
import shlex
import io
import sys
import subprocess
import hashlib
import json
import re
import shelve
import argparse

from jinja2 import Environment, FileSystemLoader
from jinja2.exceptions import TemplateNotFound


class App:
    def __init__(self):
        self.prompts_dir = os.path.expanduser("~/.prompts/")
        self.args = self.get_argparse_parser().parse_args()
        self.cache = shelve.open(os.path.expanduser("~/.prompt_cache"))
        self.env = Environment(
            loader=FileSystemLoader(self.prompts_dir),
            lstrip_blocks=True,
        )

    def run(self):
        if self.args.list:
            self.command_list()

        # args = " ".join(sys.argv[2:])

        template_name = self.args.prompt + ".j2"

        try:
            template = self.env.get_template(template_name)
        except TemplateNotFound:
            print(
                f"No such prompt: {self.args.prompt} (try `siesta --list`)",
                file=sys.stderr,
            )
            sys.exit(1)
        output = template.render(args=self.args).strip()

        print(output)

    def add_filter(self, name, func, bind_app=False):
        if bind_app:
            self.env.filters[name] = lambda *args, **kwargs: func(self, *args, **kwargs)
        else:
            self.env.filters[name] = func

    def get_argparse_parser(self):
        parser = argparse.ArgumentParser(
            prog="siesta", description="Automatize workflow with jinja2 prompts."
        )

        parser.add_argument(
            "prompt", nargs="?", help=f"A prompt template at {self.prompts_dir}"
        )
        parser.add_argument("--list", help="List all prompts", action="store_true")
        parser.add_argument("--recache", help="Rewrite to cache", action="store_true")
        parser.add_argument(
            "--verbose", help="Print completions as it comes", action="store_true"
        )
        return parser

    def command_list(self):
        for prompt in os.listdir(self.prompts_dir):
            if prompt.endswith(".j2"):
                print(prompt[:-3])
        sys.exit(0)


def filter_run(app, input, cmd="bash", label=False, silentfail=False):
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


def filter_debug(app, input):
    print(input)
    print("=== DEBUG DIE DIE ===")
    sys.exit(0)


def filter_prompt(app, prompt, model):
    # Import on-demand because its slow
    from litellm import completion

    cache_key = hashlib.sha256(f"{model}:{prompt}".encode()).hexdigest()
    if app.args.recache:
        cached = None
    else:
        cached = app.cache.get(cache_key)

    if cached is not None:
        return cached
    else:
        response = completion(
            model=model, messages=[{"content": prompt, "role": "user"}], stream=True
        )
        msg = io.StringIO()
        for chunk in response:
            delta = chunk.choices[0].delta.content
            if not delta:
                break
            msg.write(delta)
            if app.args.verbose:
                sys.stderr.write(delta)
                sys.stderr.flush()

        msgval = msg.getvalue()
        app.cache[cache_key] = msgval

        return msgval


def filter_catfiles(app, inp):
    files = re.findall(r"(\w+\/[\w/\.]+)", inp)  # BUGGED, rewrite re
    contents = io.StringIO()
    for file in files:
        if os.path.exists(file):
            with open(file, "r") as f:
                content = f.read()
                contents.write(f"=== file: {file} ===\n{content}\n======\n")
    return contents.getvalue()


def filter_code(app, inp):
    triple_quotes = re.findall(r"```(.*?)```", inp, re.DOTALL)
    single_quotes = re.findall(r"`(.*?)`", inp, re.DOTALL)
    if triple_quotes:
        return "\n".join(triple_quotes[-1].splitlines()[1:])
    if single_quotes:
        return single_quotes[-1]
    return inp


def filter_askrun(app, inp):
    print(inp)
    ask = input("[R]epeat, E[x]ecute, E[d] or [Q]uit?")
    if ask == "":
        ask = "r"

    if ask == "x":
        os.execlp("bash", "bash", "-c", inp)
    elif ask == "r":
        app.run()
    elif ask == "q":
        sys.exit(0)


def filter_quote(app, stri):
    return shlex.quote(stri)


def filter_askedit(stri):
    result = subprocess.run(
        ["dialog", "--inputbox", "Edit", "10", "100", stri],  # Example command
        text=True,  # Handle output as text (str)
        stderr=subprocess.PIPE,  # Capture only stderr
        check=True,  # Raise an exception on failure
    )
    return result.stderr


def main():
    app = App()
    app.add_filter("prompt", filter_prompt, bind_app=True)
    app.add_filter("debug", filter_debug, bind_app=True)
    app.add_filter("run", filter_run, bind_app=True)
    app.add_filter("catfiles", filter_catfiles, bind_app=True)
    app.add_filter("askrun", filter_askrun, bind_app=True)
    app.add_filter("askedit", filter_askedit)
    app.add_filter("code", filter_code, bind_app=True)
    app.add_filter("quote", shlex.quote)
    app.add_filter("json", json.loads)
    app.run()


if __name__ == "__main__":
    main()
