### Project status

We're really busy at the moment (Jan 2018) and have put development of this on hold until we start to need it internally (which is likely to be a few months). If you're interested in using this, you have a few options:

- use it in it's current state - it's pretty hacky, but worked on our limited test set
- fork it and make it better!
- use the port (https://github.com/Togusa09/powerbi-vcs-dotnet) which may be more maintained etc.

### File Format Specification

The PBIX and PBIT files are [Open Packaging Conventions files](https://en.wikipedia.org/wiki/Open_Packaging_Conventions). Within a PBIX container there are two binary files of particular note, which would require further conversion for storage within a VCS. Some of this work can be skipped by saving the file as a PBIT.

#### Binary blob format specifications
 - DataMashup: [MS-QDEFF](https://interoperability.blob.core.windows.net/files/MS-QDEFF/%5bMS-QDEFF%5d.pdf).
 - DataModel: [MS-XLDM](https://interoperability.blob.core.windows.net/files/MS-XLDM/%5bMS-XLDM%5d.pdf)
 
These can be used to further enhance the converters, if anyone ever has the time. There is no guarentee these formats are exact or current. The specifications are intended for the streams embedded in Excel files. However they are closely related (and may be identical).

&nbsp;

--- 

> NOTE: this is not yet ready to be used!

### Introduction

Power BI does not (currently) support integration with source control, which is a real pain, most notably because `*.pbi{tx}` cannot be diffed and merged. This means:

- repos blow up quickly, as even with minor changes, the entire `*.pbi{xt}` is saved.
- it's hard to collaborate as changes from two developers can't be merged, and hence changes must be made one after the other (so you're effectively limited to a single full-time developer per report).

This repo aims to improve this as much as possible (without tweaking Power BI itself) *until Powe BI itself supports this*.

> That's right ... this is only a temporary hack, and should be treated as such.

It abuses the fact that `*.pbi{tx}` files are (nearly) just (double) ZIP compressed folders which follow a specific structure.

### Installation [TODO]

Install python 3 (I recommend Anaconda if you're using Windows). Until someone writes the install script: just run the `pbivcs.py` file

### What do I get (currently)?

Say you've just made some changes to your Power BI file `apples.pbix` and you want to add it to version control. First, you'll need to export it as a Power BI Template i.e. `apples.pbit`, and then extract it into a VCS-friendly format:

```sh
pbivcs -x apples.pbit apples.pbit.vcs
```

will extract your `apples.pbit` into the VCS-friendly format at `apples.pbit.vcs`. If you choose, you can [TODO] automatically check that this will compress into a valid `pbit`. Then, for example

```sh
git commit -a -m "apples are so awesome"
```

will (assuming you've set it up as outlined below):

1. [TODO] check you haven't accidentally forgotten to export a new `pbit` from your `pbix`
2. commit `apples.pbit.vcs` to git
3. (optionally) ignore `apples.pbit` and `apples.pbix` or [TODO] replace them with chksums (or a link to a file store of all versions? depending on your CI. TODO: can we actually create an `apples.pbit.history` folder to contain these? This would ensure no `pbit` is ever over-written.)

Now, suppose your colleague had also made a change to the same report. Then a `git pull` and `git diff` might show something like this:

```sh
...
-           "value": "Apples are yummy",
+           "value": "Apples are awesome",
...
```

and you can see that your colleague has just changed the title. There aren't any major conflicts, so you can happily `git merge` and merge your work.

You then want to make another change, so you need to compress the VCS-friendly format back to your `pbit`, which is as easy as

```sh
pbivcs -c apples.pbit.vcs apples.pbit
```

(and yes, since you're super careful, you can control how overwrites etc. happen).

### Git textconv driver support
This option dumps the extracted file contents to standard out to allow for better diffs in git of files which were commited in the binary PBIT or PBIX format.

Add to repo .gitattributes file:
```
*.pbit diff=pbit
*.pbix diff=pbit
```

Add to global or local .gitconfig file:
```
[diff "pbit"]
	textconv = pbivcs -s
```

Diffs in git will do their diff on the extracted file content. Textconv diffs are only a visual guide, and can't be used to merge changes, but this provides better insight into what has changed in the power bi report.

Documentation of git textconv drivers [https://git.wiki.kernel.org/index.php/Textconv]

### Other cool features


- TODO: change control: we'll attempt to keep this as up-to-date with Power BI as possible. The version of this tool that was used will be saved in any extraction/compression process, to allow (in theory) this tool to work on a complete git history, regardless of the Power BI versions used. (Provided this tool always functioned.)
- TODO: everything's configurable to your level of comfort (e.g. always overwrite files, or check first, etc.)
- lots of configuration. There a built-in defaults (conservative safe ones), but you can also specify your own defaults (in a hierarchy of `.pbivcs.conf` files), as well as utilising environment variables, and command line arguments. See below [TODO]

### What don't I get?

- unthinking automation (at least for now):
	- you still need to manually export a `*.pbit` from your `*.pbix`
	- you have to run scripts before/after the git actions. If this solution proves to be robust, we may automate this somewhat with git hooks or filters, but I'm wary of the bugs these may introduce into the user experience.

### Configuration

We use [ConfigArgParse](https://pypi.python.org/pypi/ConfigArgParse), which means `pbivcs` has the following configurations:

- built-in defaults (which tend to be safe and conservative)
- your own `.pbivcs.conf` files
- environment variables
- command line arguments

where each levels takes precedence over the one before. The main use is the `.pbivcs.conf` files which means you can customise it to behave as you want, without having to enter the options at the command line. The location of these files is such that they must be siblings of one of the elements on the path of you input file. E.g. if you run `pbivcs -x /path/to/my/file.pbit` then the following configuration files will be used (if they exist):

- `/.pbivcs.conf`
- `/path/.pbivcs.conf`
- `/path/to/.pbivcs.conf`
- `/path/to/my/.pbivcs.conf`

where each one takes precendence over the one preceeding it. Usually this would mean you would set a global `.pbivcs.conf` at the root of your project, but means you can have further ones in different parts of the project if you want different behaviour for the odd report.

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
- [ ] after compressing, test that the decompressed version is valid (by opening in Power BI Desktop)?
- [ ] complete install instructions inc. conda environment

### Discussion

#### What about Power BI support?

[Good question.](https://ideas.powerbi.com/forums/265200-power-bi-ideas/suggestions/9677517-source-control) Unfortunately, there are no indications of when this will be provided by Power BI.

#### What about git filters?

Sure you could do something like [zippey](https://bitbucket.org/sippey/zippey). However, I think (?) this requires you to map a single file (`*.pbit`) to a single other file (in whatever format). While you could do something like in zippey (concatenating them all etc.) it'd start getting messy (especially with it still containing binary content e.g. images), and I'm not a fan. I also don't really like the idea of using automated filters (at least until I know more about how these are used in git).

#### Why not automate with git hooks?

Firstly, git hooks aren't shared between repos. Not a major, just saying.

Secondly, I don't know how things would behave in all situations. E.g. if you add the `*.pbit` and a hook runs to convert it to the VCS format. What then happens if you want to make a change to it? Anyway, if someone knows better, let me know (or submit a PR).

### Tests

- check that configargparse and use of config files behaves as expected
