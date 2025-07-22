# siesta

## Crash Course

### install

```
pip3 install git+https://github.com/ihucos/siesta.git
```

### Create your first script at `~/bin/s-commit`

```jinja2
#!/usr/bin/env siesta
# vim: set ft=jinja
{% set commit|prompt("openai/gpt-4o-mini") %}
Write a git commit message for these changes. Use few words.
  {% filter run(label=True) %}
  git diff
  {% endfilter %}
{% endset %}

{% filter run %}
git commit -am {{ commit|askedit|escape }}
{% endfilter %}
```

### mark as executable
```
chmod +x ~/bin/s-commit
```

### Use the script

```
s-commit
```

## Filters

### prompt
Ask for completion by a LLM. See list of supported models: https://docs.litellm.ai/docs/providers

### debug
Print input and exit.

### run
Run input in bash, return output

### catfiles
Cat all files found in input with labels

### askrun
Ask the user to run something

### askedit
Let the user edit a string

### code
Filter out code blocks

### quote
Shell escape

### json
Parse as JSON

