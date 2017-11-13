# 1: have scripts which extract from .pbit to .pbit.extract - gitignore .pbit (and .pbix), AND creates .pbix.chksum (which is only useful for versioning purposes - one can confirm the state of their pbix)
    # - script basically extracts .pbit to new folder .pbit.extract, but a) also extracts double-zipped content, and b) formats stuff nicely so it's readable/diffable/mergeable.
# 2: have git hooks which check, before a commit:
    # - checks that the .pbit.extract folder is up to date with the latest .pbit (i.e. they match exactly - and the .pbit hasn't been exported but user forgot to run the extract script)
    # - adds a warning (with y/n continue feedback) if the .pbix has been updated *after* the latest .pbit.extract is updated. (I.e. they maybe forgot to export the latest .pbit and extract, or exported .pbit but forgot to extract.) Note that this will be obvious in the case of only a single change (as it were) - since .pbix aren't tracked, they'll see no changes to git tracked files.

import zipfile
import os
import shutil
import converters

CONVERTERS = {
    'DataModelSchema': converters.JSONConverter('utf-16-le'),
    'DiagramState': converters.JSONConverter('utf-16-le'),
    'Report/Layout': converters.JSONConverter('utf-16-le'),
    'Report/LinguisticSchema': converters.XMLConverter('utf-16-le', False),
    '[Content_Types].xml': converters.XMLConverter('utf-8-sig', True),
    'SecurityBindings': converters.NoopConverter(),
    'Settings': converters.NoopConverter(),
    'Version': converters.NoopConverter(),
    'Report/StaticResources/': converters.NoopConverter(),
    'DataMashup': converters.DataMashupConverter(),
    'Metadata': converters.MetadataConverter()
    }


def extract_pbit(pbit_path, outdir, overwrite):
    """
    Convert a pbit to vcs format
    """
    # TODO: check ends in pbit
    # TODO: check all expected files are present (in the right order)

    # wipe output directory and create:
    if os.path.exists(outdir):
        if overwrite:
            shutil.rmtree(outdir)
        else:
            raise Exception('Output path "{0}" already exists'.format(outdir))

    os.mkdir(outdir)

    order = []

    with zipfile.ZipFile(pbit_path, compression=zipfile.ZIP_DEFLATED) as zd:

        # read items (in the order they appear in the archive)
        for name in zd.namelist():
            order.append(name)
            outpath = os.path.join(outdir, name)
            # get converter:
            conv = CONVERTERS.get(name, None)
            if conv is None:
                starters = [i for i in CONVERTERS.keys() if name.startswith(i)]
                if len(starters) != 1:
                    raise ValueError("TODO")
                conv = CONVERTERS[starters[0]]
            # convert
            conv.write_raw_to_vcs(zd.read(name), outpath)

        # write order files:
        open(os.path.join(outdir, ".zo"), 'w').write("\n".join(order))


def compress_pbit(extracted_path, compressed_path, overwrite):
    """Convert a vcs store to valid pbit."""
    # TODO: check all paths exists

    if os.path.exists(compressed_path):
        if overwrite:
            os.remove(compressed_path)
        else:
            raise Exception('Output path "{0}" already exists'.format(compressed_path))

    # get order
    with open(os.path.join(extracted_path, ".zo")) as f:
        order = f.read().split("\n")

    with zipfile.ZipFile(compressed_path, mode='w',
                         compression=zipfile.ZIP_DEFLATED) as zd:
        for name in order:
            # get converter:
            conv = CONVERTERS.get(name, None)
            if conv is None:
                starters = [i for i in CONVERTERS.keys() if name.startswith(i)]
                if len(starters) != 1:
                    raise ValueError("TODO")
                conv = CONVERTERS[starters[0]]

            # convert
            with zd.open(name, 'w') as z:
                conv.write_vcs_to_raw(os.path.join(extracted_path, name), z)


def _find_confs(path):
    """
    Find all .pbivcs.conf files (if any) furthest down the path, ordered by hierarchy i.e.
    '/path/to/my/.pbivcs.conf' would come before '/path/to/.pbivcs.conf'
    """
    
    splat = tuple(i for i in os.path.split(os.path.abspath(os.path.normpath(path))) if i)
    confs = []
    print(splat)
    for i in range(1, len(splat)):
        print(splat[:i])
        parent = os.path.join(*splat[:i])
        confpath = os.path.join(parent, '.pbivcs.conf')
        if os.path.exists(confpath):
            confs.append(confpath)
    return confs
                
if __name__ == '__main__':

    import configargparse

    parser = configargparse.ArgumentParser(description="A utility for converting *.pbit files to and from a VCS-friendly format")
    parser.add_argument('input', type=str, help="the input path")
    parser.add_argument('output', type=str, help="the output path")
    parser.add_argument('-x', action='store_true', dest="extract", default=True, help="extract pbit at INPUT to VCS-friendly format at OUTPUT")
    parser.add_argument('-c', action='store_false', dest="extract", default=True, help="compress VCS-friendly format at INPUT to pbit at OUTPUT")
    parser.add_argument('--over-write', action='store_true', dest="overwrite", default=False, help="if present, allow overwriting of OUTPUT. If not, will fail if OUTPUT exists")
    # parse args first to get input path:
    input_path = parser.parse_args().input
    # now set config files for parser:
    parser._default_config_files = _find_confs(input_path)
    # now parse again to get final args:
    args = parser.parse_args()

    if args.input == args.output:
        parser.error('Error! Input and output paths cannot be same')

    if args.extract:
        extract_pbit(args.input, args.output, args.overwrite)
    else:
        compress_pbit(args.input, args.output, args.overwrite)
