# method:

# 1: have scripts which extract from .pbit to .pbit.extract - gitignore .pbit (and .pbix), AND creates .pbix.chksum (which is only useful for versioning purposes - one can confirm the state of their pbix)
    # - script basically extracts .pbit to new folder .pbit.extract, but a) also extracts double-zipped content, and b) formats stuff nicely so it's readable/diffable/mergeable.
# 2: have git hooks which check, before a commit:
    # - checks that the .pbit.extract folder is up to date with the latest .pbit (i.e. they match exactly - and the .pbit hasn't been exported but user forgot to run the extract script)
    # - adds a warning (with y/n continue feedback) if the .pbix has been updated *after* the latest .pbit.extract is updated. (I.e. they maybe forgot to export the latest .pbit and extract, or exported .pbit but forgot to extract.) Note that this will be obvious in the case of only a single change (as it were) - since .pbix aren't tracked, they'll see no changes to git tracked files.

# 1: must be one file -> one file, therefore the extracted zip archive must be merged into one
# 2: check pbix hasn't been updated ... save checksum to txt file

# Q: will this work when doing complex merges? I.e. small changes will be OK, but trying to merge two massive changes will probably cause merge issues - and good luck to the user trying to resolve this!

import zipfile
import json
import re
from io import BytesIO
import ast
from chardet import detect
import struct

#import xml.dom.minidom
from lxml import etree
import tempfile
import os
import xml.etree.ElementTree as ET
from xml.parsers.expat import ExpatError
import xml.parsers.expat.errors as xmlerrors
import shutil
from decimal import Decimal

ENCODINGS = {
    'DataModelSchema': 'utf-16-le',
    'DiagramState': 'utf-16-le',
    'Report/Layout': 'utf-16-le',
    'Report/LinguisticSchema': 'utf-16-le',
    '[Content_Types].xml': 'utf-8-sig'
    }



# TODO: order elements alphabetically, where possible, to ensure consistent tidying


def xml_raw_to_vcs(b, enc, xml_declaration=True):
    parser = etree.XMLParser(remove_blank_text=True)
    # if encoding specified, we need to do a hack as the 'encoding' attribute get's removed with toprettyxml (unless you specify it as an argument)
    m = re.match(b'(^.{,4}\<\?xml [^\>]*)encoding="[a-z0-9_\-]+"', b)
    # TODO: check if enc != m
    if m:
        root = etree.fromstring(b, parser)
    else:
        root = etree.fromstring(b.decode(enc), parser)
    return etree.tostring(root, pretty_print=True, xml_declaration=xml_declaration, encoding='utf-8')

def xml_vcs_to_raw(b, enc, xml_declaration=True):
        
    parser = etree.XMLParser(remove_blank_text=True)
    root = etree.fromstring(b, parser)
    lxml_enc = enc.replace('-le', '').replace('-sig', '')
    return etree.tostring(root, pretty_print=False, xml_declaration=xml_declaration, encoding=lxml_enc).decode(lxml_enc).encode(enc)

def jsonify_embedded_json(v):    
    if isinstance(v, str):
        try:
            d = json.loads(v)
            if isinstance(d, (dict, list)):
                return { '__pbiextracted__': d }
            else:
                return v
        except Exception as e:
            return v
    elif isinstance(v, dict):
        return {kk: jsonify_embedded_json(vv) for kk, vv in v.items()}
    elif isinstance(v, list):
        return [jsonify_embedded_json(vv) for vv in v]
    else:
        return v
    
def undo_jsonify_embedded_json(v):
    if isinstance(v, dict):
        if len(v) == 1 and '__pbiextracted__' in v:
            return json.dumps(v['__pbiextracted__'], separators=(',', ':'), ensure_ascii=False)
        return {kk: undo_jsonify_embedded_json(vv) for kk, vv in v.items()}
    elif isinstance(v, list):
        return [undo_jsonify_embedded_json(vv) for vv in v]
    else:
        return v

# sometimes the json has big JSON strings inside the JSON - and these obviously don't get prettified nicely. So, a hack:    
def json_raw_to_vcs(raw):
    return json.dumps(jsonify_embedded_json(json.loads(raw)), indent=2, ensure_ascii=False)

def json_vcs_to_raw(vcs):
    return json.dumps(undo_jsonify_embedded_json(json.loads(vcs)), separators=(',', ':'), ensure_ascii=False)

def extract_pbit(fpath):
    # TODO: check ends in pbit
    # TODO: check all expected files are present (in the right order)
    outdir = fpath + '.extract'

    # wipe output directory and create:
    if os.path.exists(outdir):
        shutil.rmtree(outdir)
    os.mkdir(outdir)

    order = []

    with zipfile.ZipFile(fpath, compression=zipfile.ZIP_DEFLATED) as zd:

        # read items (in the order they appear in the archive)
        for zf in zd.infolist():
            name = zf.filename
            order.append(name)
            outfile = os.path.join(outdir, name)
            os.makedirs(os.path.dirname(outfile), exist_ok=True) # create folder if needed
            
            if name in ('DataModelSchema', 'DiagramState', 'Report/Layout'):
                out = json_raw_to_vcs(zd.read(name).decode(ENCODINGS[name]))
                open(outfile, 'w').write(out)
            elif name in ('Report/LinguisticSchema', '[Content_Types].xml'):
                out = xml_raw_to_vcs(zd.read(name), ENCODINGS[name], xml_declaration=(name != 'Report/LinguisticSchema'))
                open(outfile, 'wb').write(out)
            elif name in ('SecurityBindings', 'Settings', 'Version') or name.startswith("Report/StaticResources"):
                # spit these straight back out:
                open(outfile, 'wb').write(zd.read(name))
            elif name == 'Metadata':
                # OK, this content is nearly readable, apart from a few stray bytes. To aid merges/diffs, we'll split into into multiple lines.
                s = repr(zd.open(name).read())
                if "\n" in s:
                    raise ValueError("TODO: '\n' is used as a terminator but already exists in string! Someone needs to write some code to dynamically pick the (possibly multi-byte) terminator ...")
                splat = re.split('(\\\\x[0-9a-f]{2})([^\\\\x])', s)
                out = ''
                for i, spl in enumerate(splat):
                    if i % 3 == 2:
                        out += '\n'
                    out += spl
                open(outfile, 'w').write(out)
            elif name == 'DataMashup':

                # format:
                #   - 4 null bytes
                #   - 4 bytes representing little-endian int for length of next zip
                #   - bytes (of length above) as zip
                #   - 4 bytes representing little-endian int for length of next xml
                #   - utf-8-sig xml of above length
                #   - 4 bytes representing little-endian int - which seems to be 34 more than the one two below:
                #   - 4 null bytes
                #   - 4 bytes representing little-endian int for length of next xml
                #   - xml of this length
                #   - not sure what the remainder is ...

                b = zd.read(name)
                if b[:4] != b'\x00\x00\x00\x00':
                    raise ValueError("TODO")
                len1 = int.from_bytes(b[4:8], byteorder="little")
                start1 = 8
                end1 = start1 + len1
                zip1 = b[start1:end1]
                start2 = end1 + 4
                len2 = int.from_bytes(b[end1:start2], byteorder="little")
                end2 = start2 + len2
                xml1 = b[start2:end2]
                b8 = b[end2:end2+8]
                start3 = end2 + 12
                len3 = int.from_bytes(b[end2 + 8: start3], byteorder="little")
                if int.from_bytes(b[end2:end2+4], "little") - len3 != 34:
                    raise ValueError("TODO")
                end3 = start3 + len3
                xml2 = b[start3:end3]
                extra = b[end3:]
                                
                # extract header zip:
                with zipfile.ZipFile(BytesIO(zip1)) as zd2:
                    order2 = []
                    # read items (in the order they appear in the archive)
                    for name2 in zd2.namelist():
                        order2.append(name2)
                        outfile = os.path.join(outdir, 'DataMashup', name2)
                        os.makedirs(os.path.dirname(outfile), exist_ok=True) # create folder if needed
                        if name2.endswith('.xml'):
                            out = xml_raw_to_vcs(zd2.read(name2), 'utf-8-sig')
                            open(outfile, 'wb').write(out)
                        elif name2 == 'Formulas/Section1.m':
                            # it's good:
                            open(outfile, 'wb').write(zd2.read(name2))
                        else:
                            raise ValueError("TODO")
                
                # write order:
                open(os.path.join(outdir, 'DataMashup', ".zo"), 'w').write("\n".join(order2))

                # now write the xmls and bytes between:
                #open(os.path.join(outdir, 'DataMashup', "1.int"), 'wb').write(b[4:8])
                open(os.path.join(outdir, 'DataMashup', "3.xml"), 'wb').write(xml_raw_to_vcs(xml1, 'utf-8-sig'))
                open(os.path.join(outdir, 'DataMashup', "6.xml"), 'wb').write(xml_raw_to_vcs(xml2, 'utf-8-sig'))
                open(os.path.join(outdir, 'DataMashup', "7.bytes"), 'wb').write(extra)
                
            else:
                raise ValueError(name + " is not an expected member of a pbit archive!")

            
            # write order:
            open(os.path.join(outdir, ".zo"), 'w').write("\n".join(order))

def compress_pbit(fpath):

    compressed_path = fpath + '.extract'

    # TODO: check all paths exists

    # get order
    order = open(os.path.join(compressed_path, ".zo")).read().split("\n")
    
    with zipfile.ZipFile(fpath + '.recompressed', mode='w', compression=zipfile.ZIP_DEFLATED) as zd:

        for name in order:
            if name in ('DataModelSchema', 'DiagramState', 'Report/Layout'):
                out = json_vcs_to_raw(open(os.path.join(compressed_path, name.replace("/", os.path.sep)), 'r').read()).encode(ENCODINGS[name])
                #print(out)
                with zd.open(name, 'w') as z:
                    z.write(out)
            elif name in ('Report/LinguisticSchema', '[Content_Types].xml'):
                out = xml_vcs_to_raw(open(os.path.join(compressed_path, name.replace("/", os.path.sep)), 'rb').read(), ENCODINGS[name], xml_declaration=(name != 'Report/LinguisticSchema'))
                with zd.open(name, 'w') as z:
                    z.write(out)
            elif name in ('SecurityBindings', 'Settings', 'Version') or name.startswith("Report/StaticResources"):
                out = open(os.path.join(compressed_path, name.replace("/", os.path.sep)), 'rb').read()
                with zd.open(name, 'w') as z:
                    z.write(out)
            elif name == "Metadata":
                out = open(os.path.join(compressed_path, name)).read()
                out = out.replace('\n', '')
                out = ast.literal_eval(out)
                with zd.open(name, 'w') as z:
                    z.write(out)
            elif name == "DataMashup":
                b = BytesIO()
                with zipfile.ZipFile(b, mode='w', compression=zipfile.ZIP_DEFLATED) as zd2:
                    order2 = open(os.path.join(compressed_path, "DataMashup", ".zo")).read().split("\n")
                    for name2 in order2:
                        if name2.endswith('.xml'):
                            out = xml_vcs_to_raw(open(os.path.join(compressed_path, "DataMashup", name2), 'rb').read(), enc='utf-8-sig')
                        elif name2 == 'Formulas/Section1.m':
                            out = open(os.path.join(compressed_path, "DataMashup", name2), 'rb').read()
                        else:
                            raise ValueError("TODO")
                        with zd2.open(name2, 'w') as z2:
                            z2.write(out)

                # add stuff:
                with zd.open(name, 'w') as z:

                    # write header
                    z.write(b'\x00\x00\x00\x00')

                    # write zip
                    #priorziplen = open(os.path.join(compressed_path, 'DataMashup', "1.int"), 'rb').read()
                    #if priorziplen != thisziplen:
                    #    raise ValueError("TODO")
                        #z.write(struct.pack("<i", thisziplen)
                    z.write(struct.pack("<i", b.tell()))
                    b.seek(0)
                    z.write(b.read())

                    # write first xml:
                    xmlb = xml_vcs_to_raw(open(os.path.join(compressed_path, 'DataMashup', "3.xml"), 'rb').read(), 'utf-8-sig')
                    z.write(struct.pack("<i", len(xmlb)))
                    z.write(xmlb)

                    # write second xml:
                    xmlb = xml_vcs_to_raw(open(os.path.join(compressed_path, 'DataMashup', "6.xml"), 'rb').read(), 'utf-8-sig')
                    z.write(struct.pack("<i", len(xmlb) + 34))
                    z.write(b'\x00\x00\x00\x00')
                    z.write(struct.pack("<i", len(xmlb)))
                    z.write(xmlb)

                    # write the rest:
                    z.write(open(os.path.join(compressed_path, 'DataMashup', "7.bytes"), 'rb').read())

            else:
                print(name)
                raise ValueError("TODO")


if __name__ == '__main__':

    sampledir = os.path.join(os.path.dirname(__name__), 'samples')
    for fname in os.listdir(sampledir):
        if fname.endswith(".pbit"):
            print(fname)
            extract_pbit(os.path.join(sampledir, fname))
            compress_pbit(os.path.join(sampledir, fname))
            break