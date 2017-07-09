> NOTE: this is not yet ready to be used!

### Introduction

Power BI does not (currently) support integration with source control, which is a real pain, most notably because `*.pbi{tx}` cannot be diffed and merged. This means:

- repos blow up quickly, as even with minor changes, the entire `*.pbi{xt}` is saved.
- it's hard to collaborate as changes from two developers can't be merged, and hence changes must be made one after the other (so you're effectively limited to a single full-time developer per report).

This repo aims to improve this as much as possible, without tweaking Power BI itself. It abuses the fact that `*.pbi{tx}` files are (nearly) just (double) ZIP compressed folders which follow a specific structure. Of course, if Power BI develops further and these structures change, this solution may become invalid.

### What do I get?

You have to manually export a `*.pbit` from your `*.pbix` (unless someones knows some more tricks?). Then

- before you commit, you run a script which extracts your `*.pbit` into a git-friendly form, which is what's recorded in the repo (not the `*.pbi{tx}`).
- this means diffs and merges can happen (to an extent)
- when you pull an update from the repo, the git-friendly form can be merged (and you can resolve any conflicts etc.). You then run a script to create a `*.pbit` from the git-friendly form, which you can then oepn with Power BI desktop as per usual.

In addition:

- TODO: you'll get warnings about ...
- TODO: change control: we'll attempt to keep this as up-to-date with Power BI as possible. The version of this tool that was used will be saved in any extraction/compression process, to allow (in theory) this tool to work on a complete git history, regardless of the Power BI versions used. (Provided this tool always functioned.)
- everything's configurable to your level of comfort (e.g. always overwrite files, or check first, etc.)

### What don't I get?

- automation (at least for now):
	- you still need to manually export a `*.pbit` from your `*.pbix`
	- you have to run scripts before/after the git actions. If this solution proves to be robust, we may automate this somewhat with git hooks or filters.

### Roadmap

- figure out how to export `*.pbit` from `*.pbix` automatically
- support other VCS
- automate git somewhat with hooks or filters

### Contributing

TODO

### License

See `./license.md`.