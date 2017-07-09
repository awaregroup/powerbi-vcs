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

import xml.dom.minidom
import tempfile
import os
import xml.etree.ElementTree as ET
from xml.parsers.expat import ExpatError
import xml.parsers.expat.errors as xmlerrors
import shutil


def tidy_xml(body):

    # TODO: order elements alphabetically, where possible, to ensure consistent tidying

    x = xml.dom.minidom.parseString(body)

    # if encoding specified, we need to do a hack as the 'encoding' attribute get's removed with toprettyxml (unless you specify it as an argument)
    m = re.match('^\<\?xml [^\>]*encoding="([a-z0-9_\-]+)"', body)
    out = None
    if m:
        enc = m.group(1)
        out = x.toprettyxml(indent="  ", encoding=enc).decode(enc)
    else:
        out = x.toprettyxml(indent="  ")

    # let's just check all is OK:
    """
    pt = ""
    rt = ""
    print(body[:100])
    minified = re.sub('\>\n[\t ]+\<', '><', out).replace('\n', '').replace('/>', ' />')
    for l, (raw, parsed) in enumerate(zip(body, minified)):
        pt += parsed
        rt += raw
        if (raw != parsed):
            print("failed at " + str(l))
            print(body[l-50:l+50])
            print(minified[l-50:l+50])
            break
    #print(x.toprettyxml(indent="", newl="", encoding='utf-8'))
    #print(s[xmlstart:xmlend])
    assert minified == body
    """
    return out      

def untidy_xml(str):

    x = xml.dom.minidom.parseString(str)

    # if encoding specified, we need to do a hack as the 'encoding' attribute get's removed with toprettyxml (unless you specify it as an argument)
    m = re.match('^\<\?xml [^\>]*encoding="([a-z0-9_\-]+)"', str)
    out = None
    if m:
        enc = m.group(1)
        return x.toprettyxml(indent="", newl="", encoding=enc).decode(enc)
    return x.toprettyxml(indent="", newl="")

def _tidy_json_str(v):

    # TODO: order elements alphabetically, where possible, to ensure consistent tidying
    
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
        return {kk: _tidy_json_str(vv) for kk, vv in v.items()}
    elif isinstance(v, list):
        return [_tidy_json_str(vv) for vv in v]
    else:
        return v
    
def _untidy_json_str(v):

    if isinstance(v, dict):
        if len(v) == 1 and '__pbiextracted__' in v:
            return json.dumps(v['__pbiextracted__'])
        return {kk: _untidy_json_str(vv) for kk, vv in v.items()}
    elif isinstance(v, list):
        return [_untidy_json_str(vv) for vv in v]
    else:
        return v

def tidy_json(body):

    # sometimes the json has big JSON strings inside the JSON - and these obviously don't get prettified nicely. So, a hack:
    d = _tidy_json_str(json.loads(body))
    return json.dumps(d, indent=2)

def untidy_json(str):

    d = _untidy_json_str(json.loads(str))
    return json.dumps(d)

def extract_pbit(fpath):
    # TODO: check ends in pbit
    # TODO: check all expected files are present (in the right order)
    outdir = fpath + '.extract'

    # wipe output directory and create:
    if os.path.exists(outdir):
        shutil.rmtree(outdir)
    os.mkdir(outdir)

    with zipfile.ZipFile(fpath, compression=zipfile.ZIP_DEFLATED) as zd:

        # read items (in the order they appear in the archive)
        for zf in zd.infolist():
            name = zf.filename
            outfile = os.path.join(outdir, name)
            os.makedirs(os.path.dirname(outfile), exist_ok=True) # create folder if needed
            
            if name in ('DataModelSchema', 'DiagramState', 'Report/Layout'):
                out = tidy_json(zd.read(name).decode('utf-16'))
                open(outfile, 'w').write(out)
            elif name in ('Report/LinguisticSchema', '[Content_Types].xml'):
                out = tidy_xml(zd.read(name).decode('utf-8-sig'))
                open(outfile, 'w').write(out)
            elif name in ('SecurityBindings', 'Settings', 'Version') or name.startswith("Report/StaticResources"):
                # spit these straight back out:
                open(outfile, 'wb').write(zd.read(name))
            elif name == 'Metadata':
                # OK, this content is nearly readable, apart from a few stray bytes. To aid merges/diffs, we'll split into into multiple lines.
                s = repr(zd.open(name).read())
                splat = re.split('(\\\\x[0-9a-f]{2})([^\\\\x])', s)
                out = ''
                for i, spl in enumerate(splat):
                    if i % 3 == 2:
                        out += '\n'
                    out += spl
                open(outfile, 'w').write(out)
            elif name == 'DataMashup':

                # OK, this one is a bit funny: from what we can make of it, it's got another zip archive in the head, then a short XML snippet, then some bytes, then a longer XML, then some more bytes.
                #   NOTE: we're assuming that structure from now on, i.e. we're not going to handle 3 xmls snippets until we see an example of them.
                # We'll extract the archive separately, but just keep the tail as-is, except for formatting the xml nicely and ascii-ing the bytes. (That is, we don't split them out. We keep them mixed, but make them human readable, and have a specific format so we can undo everything.)
                
                s = zd.read(name)
                sl = len(s)
                
                # strip out xml bits:
                xmls = []
                for xmlstart in sorted(list(set([m.start() for m in re.finditer(b'<\?xml ', s)]))):
                    
                    # use incremental parser, and keep adding characters until it bails, then remove characters until we get a nice parse:
                    # NOTE: if there was a nice way of mapping parsed elements to original source, we could avoid feeding character by character, and just feed the entire thing, and then find the end location of the last successfully parsed element before it bailed. Unfortunately, I can't find that.
                    # NOTE: you could provide a BytesIO wrapper and use tell() - but that only works if buffer size = 1, which is the same as passing character by character anyway.
                    # NOTE: we could optimize this somewhat by doing a binary search (e.g. if first half parses fine, no need to do it character-by-character) or similar ... but for now I can't be bothered.
                    xmlend = xmlstart                    
                    parser = ET.XMLPullParser(['end'])
                    for c in s[xmlstart:]:
                        parser.feed(chr(c))
                        try:
                            list(parser.read_events())
                            xmlend += 1
                        except (ET.ParseError, ExpatError) as e:
                            msg = xmlerrors.messages[e.code]
                            if msg == xmlerrors.XML_ERROR_JUNK_AFTER_DOC_ELEMENT:
                                pass
                            elif msg == xmlerrors.XML_ERROR_INVALID_TOKEN:
                                pass
                            else:
                                print(e)
                                raise ValueError("TODO")
                            break
                    if xmlend >= sl:
                        raise ValueError("TODO")
                    
                    # remove any trailing characters until we pass:
                    xmlstr = s[xmlstart:xmlend]
                    decoded = None
                    while len(xmlstr) > 0:
                        try:
                            decoded = tidy_xml(xmlstr.decode('utf-8'))
                            break
                        except Exception as e:
                            xmlstr = xmlstr[:-1]
                    
                    if decoded is None:
                        raise ValueError("TODO")
                    
                    xmls.append({
                        'start': xmlstart,
                        'end': xmlend,
                        'tidyxml': decoded
                        })
                
                assert len(xmls) == 2, "this has been designed assuming only two xml chunks ..."
                
                # extract header zip:
                with zipfile.ZipFile(BytesIO(s[:xmls[0]['start']])) as zd2:
                    # read items (in the order they appear in the archive)
                    for name2 in zd2.namelist():
                        outfile = os.path.join(outdir, 'DataMashup', name2)
                        os.makedirs(os.path.dirname(outfile), exist_ok=True) # create folder if needed
                        if name2.endswith('.xml'):
                            out = tidy_xml(zd2.read(name2).decode('utf-8-sig'))
                            open(outfile, 'w').write(out)
                        elif name2 == 'Formulas/Section1.m':
                            # it's good:
                            open(outfile, 'wb').write(zd2.read(name2))
                        else:
                            raise ValueError("TODO")
            else:
                raise ValueError(name + " is not an expected member of a pbit archive!")

def compress_pbit(fpath):

    compressed_path = fpath + '.extract'

    # TODO: check all paths exists
    
    with zipfile.ZipFile(fpath + '2', mode='w', compression=zipfile.ZIP_DEFLATED) as zd:

        for name in ('DataModelSchema', 'DiagramState', 'Report/Layout'):
            out = untidy_json(open(os.path.join(compressed_path, name.replace("/", os.path.sep)), 'r').read()).encode('utf-16')
            #print(out)
            with zd.open(name, 'w') as z:
                z.write(out)
        for name in ('Report/LinguisticSchema', '[Content_Types].xml'):
            out = untidy_xml(open(os.path.join(compressed_path, name.replace("/", os.path.sep))).read()).encode('utf-8-sig')
            with zd.open(name, 'w') as z:
                z.write(out)
        for name in ('SecurityBindings', 'Settings', 'Version'):
            out = open(os.path.join(compressed_path, name.replace("/", os.path.sep)), 'rb').read()
            with zd.open(name, 'w') as z:
                z.write(out)

        # metadata
        out = open(os.path.join(compressed_path, 'MetaData')).read()
        out = out.replace('\n', '')
        out = ast.literal_eval(out)
        with zd.open(name, 'w') as z:
            z.write(out)

        # datamashup

        """
                # OK, this one is a bit funny: from what we can make of it, it's got another zip archive in the head, then a short XML snippet, then some bytes, then a longer XML, then some more bytes.
                #   NOTE: we're assuming that structure from now on, i.e. we're not going to handle 3 xmls snippets until we see an example of them.
                # We'll extract the archive separately, but just keep the tail as-is, except for formatting the xml nicely and ascii-ing the bytes. (That is, we don't split them out. We keep them mixed, but make them human readable, and have a specific format so we can undo everything.)
                
                s = zd.read(name)
                sl = len(s)
                
                # strip out xml bits:
                xmls = []
                for xmlstart in sorted(list(set([m.start() for m in re.finditer(b'<\?xml ', s)]))):
                    
                    # use incremental parser, and keep adding characters until it bails:
                    # NOTE: if there was a nice way of mapping parsed elements to original source, we could avoid feeding character by character, and just feed the entire thing, and then find the end location of the last successfully parsed element before it bailed. Unfortunately, I can't find that.
                    # NOTE: you could provide a BytesIO wrapper and use tell() - but that only works if buffer size = 1, which is the same as passing character by character anyway.
                    # NOTE: we could optimize this somewhat by doing a binary search (e.g. if first half parses fine, no need to do it character-by-character) or similar ... but for now I can't be bothered.
                    xmlend = xmlstart                    
                    parser = ET.XMLPullParser(['end'])
                    for c in s[xmlstart:]:
                        parser.feed(chr(c))
                        try:
                            list(parser.read_events())
                        except Exception as e:
                            break
                        xmlend += 1
                    if xmlend >= sl:
                        raise ValueError("TODO")

                    # cool, now parse it fully and pretty print it:
                    xmls.append({
                        'start': xmlstart,
                        'end': xmlend,
                        'tidyxml': tidy_xml(s[xmlstart:xmlend].decode('utf-8'))
                        })
                
                assert len(xmls) == 2, "this has been designed assuming only two xml chunks ..."
                
                # extract header zip:
                with zipfile.ZipFile(BytesIO(s[:xmls[0]['start']])) as zd2:
                    # read items (in the order they appear in the archive)
                    for name2 in zd2.namelist():
                        if name2.endswith('.xml'):
                            print(zd2.read(name2))
                            out = tidy_xml(zd2.read(name2).decode('utf-8-sig'))
                            open(os.path.join(outdir, 'DataMashup', name2.replace("/", os.path.sep)), 'w').write(out)
                        elif name2 == 'Formulas/Section1.m':
                            # it's good:
                            open(os.path.join(outdir, 'DataMashup', name2.replace("/", os.path.sep)), 'wb').write(zd2.read(name2))
                        else:
                            raise ValueError("TODO")
            else:
                raise ValueError("TODO")
                """

if __name__ == '__main__':

    sampledir = 'D:/testing/samples'
    for fname in os.listdir(sampledir):
        if fname.endswith(".pbit"):
            print(fname)
            extract_pbit(os.path.join(sampledir, fname))
            #compress_pbit('Aware Col Demo.pbit')