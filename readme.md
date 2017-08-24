> NOTE: this is not yet ready to be used!

### Introduction

Power BI does not (currently) support integration with source control, which is a real pain, most notably because `*.pbi{tx}` cannot be diffed and merged. This means:

- repos blow up quickly, as even with minor changes, the entire `*.pbi{xt}` is saved.
- it's hard to collaborate as changes from two developers can't be merged, and hence changes must be made one after the other (so you're effectively limited to a single full-time developer per report).

This repo aims to improve this as much as possible (without tweaking Power BI itself) *until Powe BI itself supports this*.

> That's right ... this is only a temporary hack, and should be treated as such.

It abuses the fact that `*.pbi{tx}` files are (nearly) just (double) ZIP compressed folders which follow a specific structure.

### What do I get (currently)?

You have to manually export a `*.pbit` from your `*.pbix` (unless someones knows some more tricks?). Then

- before you commit, you run a script which extracts your `*.pbit` into a git-friendly form, which is what's recorded in the repo (not the `*.pbi{tx}`).
- this means diffs and merges can happen (within reason - you want be able to merge two complete rewrites, as you'd expect)
- when you pull an update from the repo, the git-friendly form can be merged (and you can resolve any conflicts etc.). You then run a script to create a `*.pbit` from the git-friendly form, which you can then open with Power BI desktop as per usual.

TODO: add example for the above.

In addition:

- TODO: you'll get warnings about ...
- TODO: change control: we'll attempt to keep this as up-to-date with Power BI as possible. The version of this tool that was used will be saved in any extraction/compression process, to allow (in theory) this tool to work on a complete git history, regardless of the Power BI versions used. (Provided this tool always functioned.)
- TODO: everything's configurable to your level of comfort (e.g. always overwrite files, or check first, etc.)

### What don't I get?

- automation (at least for now):
	- you still need to manually export a `*.pbit` from your `*.pbix`
	- you have to run scripts before/after the git actions. If this solution proves to be robust, we may automate this somewhat with git hooks or filters, but I'm wary of the bugs these may introduce into the user experience.

### Roadmap

- figure out how to export `*.pbit` from `*.pbix` automatically
- support other VCS ...
- some git utility scripts e.g. to remove old `*.pbix` from repo and rebuild it as if we'd been using this tool the whole way along (i.e. replace `*.pbit` with the extracted version so we can hence track diffs)
- automate git somewhat with hooks or filters

### Contributing

TODO

### License

See `./license.md`.

### TODO (before 'release')

- [ ] argparse etc.
- [ ] provision script that sets up given repo: provide git template .gitignore and .gitattribtes (e.g. to ignore `*.pbix` or smudge them to a checksum, and ignore changed `modifiedTime` etc. in diffs.
- [ ] tests ... how?
- [ ] change control ... save version of tool used?
- [ ] configuration file that sets defaults
- [ ] after compressing, test that the decompressed version is valid (by opening in Power BI Desktop)?
- [ ] install instructions inc. conda environment

### Discussion

#### What about Power BI support?

[Good question.](https://ideas.powerbi.com/forums/265200-power-bi-ideas/suggestions/9677517-source-control) Unfortunately, there are no indications of when this will be provided by Power BI.

#### What about git filters?

Sure you could do something like [zippey](https://bitbucket.org/sippey/zippey). However, I think (?) this requires you to map a single file (`*.pbit`) to a single other file (in whatever format). While you could do something like in zippey (concatenating them all etc.) it'd start getting messy (especially with it still containing binary content e.g. images), and I'm not a fan. I also don't really like the idea of using automated filters (at least until I know more about how these are used in git).

#### Why not automate with git hooks?

Firstly, git hooks aren't shared between repos. Not a major, just saying.

Secondly, I don't know how things would behave in all situations. E.g. if you add the `*.pbit` and a hook runs to convert it to the VCS format. What then happens if you want to make a change to it? Anyway, if someone knows better, let me know (or submit a PR).
