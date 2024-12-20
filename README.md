# siesta

## install

pip install git+https://github.com/ihucos/siesta.git

## Create your first workflow at `~/.prompts`

```
# ~/.prompts/commit.j2
{% set commit|prompt("openai/gpt-4o") %}
Write a git commit message for these changes. Use few words.
{{ "git diff"|run(label=True) }}
{% endset %}

{% filter run %}
git commit -am {{ commit|askedit|quote }}
{% endfilter %}
```

## Use the workflow

```
siesta commit
```