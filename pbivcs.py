# 1: have scripts which extract from .pbit to .pbit.extract - gitignore .pbit (and .pbix), AND creates .pbix.chksum (which is only useful for versioning purposes - one can confirm the state of their pbix)
    # - script basically extracts .pbit to new folder .pbit.extract, but a) also extracts double-zipped content, and b) formats stuff nicely so it's readable/diffable/mergeable.
# 2: have git hooks which check, before a commit:
    # - checks that the .pbit.extract folder is up to date with the latest .pbit (i.e. they match exactly - and the .pbit hasn't been exported but user forgot to run the extract script)
    # - adds a warning (with y/n continue feedback) if the .pbix has been updated *after* the latest .pbit.extract is updated. (I.e. they maybe forgot to export the latest .pbit and extract, or exported .pbit but forgot to extract.) Note that this will be obvious in the case of only a single change (as it were) - since .pbix aren't tracked, they'll see no changes to git tracked files.

import zipfile
import json
import re
from io import BytesIO
import struct
from lxml import etree
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


def extract_pbit(pbit_path):
    """
    Convert a pbit to vcs format
    """
    # TODO: check ends in pbit
    # TODO: check all expected files are present (in the right order)
    outdir = pbit_path + '.extract'

    # wipe output directory and create:
    if os.path.exists(outdir):
        shutil.rmtree(outdir)
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

def compress_pbit(compressed_dir):
    """
    Convert a vcs store to valid pbit.
    """
    # TODO: check all paths exists

    # get order
    order = open(os.path.join(compressed_dir, ".zo")).read().split("\n")
    
    with zipfile.ZipFile(compressed_dir + '.recompressed', mode='w', compression=zipfile.ZIP_DEFLATED) as zd:

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
                conv.write_vcs_to_raw(os.path.join(compressed_dir, name), z)

if __name__ == '__main__':

    sampledir = os.path.join(os.path.dirname(__name__), 'samples')
    for fname in os.listdir(sampledir):
        if fname.endswith(".pbit"):
            print(fname)
            extract_pbit(os.path.join(sampledir, fname))
            compress_pbit(os.path.join(sampledir, fname + '.extract'))
            break