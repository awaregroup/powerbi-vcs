import zipfile
import json
import re
from io import BytesIO
import struct
from lxml import etree
import os
import ast


class Converter:

    def raw_to_vcs(self, b, *args, **kwargs):
        raise NotImplementedError("Converter.raw_to_vcs must be extended!")

    def vcs_to_raw(self, b, *args, **kwargs):
        raise NotImplementedError("Converter.vcs_to_raw must be extended!")

    def write_raw_to_vcs(self, b, vcspath, *args, **kwargs):
        os.makedirs(os.path.dirname(vcspath), exist_ok=True)
        with open(vcspath, 'wb') as f:
            f.write(self.raw_to_vcs(b, *args, **kwargs))

    def write_vcs_to_raw(self, vcspath, rawzip, *args, **kwargs):
        with open(vcspath, 'rb') as f:
            rawzip.write(self.vcs_to_raw(f.read(), *args, **kwargs))


class NoopConverter(Converter):

    def raw_to_vcs(self, b):
        return b

    def vcs_to_raw(self, b):
        return b


class XMLConverter(Converter):

    LXML_ENCODINGS = {
        'utf-8-sig': 'utf-8',
        'utf-16-le': 'utf-16'
        }

    def __init__(self, encoding, xml_declaration):
        self.encoding = encoding
        self.xml_declaration = xml_declaration
        # Note that lxml doesn't recognize the encoding names e.g. 'utf-8-sig' or 'utf-16-le' (they're recognized as
        # 'utf-8' and 'utf-16' respectively). Hence the little hack below:
        self.lxml_encoding = self.LXML_ENCODINGS.get(encoding, encoding)

    def raw_to_vcs(self, b):
        """ Convert xml from the raw pbit to onse suitable for version control - i.e. nicer encoding, pretty print, etc. """

        parser = etree.XMLParser(remove_blank_text=True)

        # If no encoding is specified in the XML, all is well - we can decode it then pass the unicode to the parser.
        # However, if encoding is specified, then lxml won't accept an already decoded string - so we have to pass it
        # the bytes (and let it decode).
        m = re.match(b'^.{,4}\<\?xml [^\>]*encoding=[\'"]([a-z0-9_\-]+)[\'"]', b)
        if m:
            xml_encoding = m.group(1).decode('ascii')
            if xml_encoding.lower() != self.lxml_encoding.lower():
                raise ValueError("TODO")
            root = etree.fromstring(b, parser)
        else:
            root = etree.fromstring(b.decode(self.encoding), parser)

        # return pretty-printed, with XML, in UTF-8
        return etree.tostring(root, pretty_print=True, xml_declaration=self.xml_declaration, encoding='utf-8')

    def vcs_to_raw(self, b):
        """ Convert from the csv version on xml to the raw form - i.e. not pretty printing and getting the encoding right """

        parser = etree.XMLParser(remove_blank_text=True)
        root = etree.fromstring(b, parser) # note that vcs is always in UTF-8, which is encoded in the xml, so no need to specify
        # We do the decode and encode at the end so that e.g. if it's meant to be 'utf-8-sig', lxml_enc will be 'utf-8'
        # (which will be encoded in the xml), but we need to add the three -sig bytes to make it 'utf-8-sig'.
        return etree.tostring(root, pretty_print=False, xml_declaration=self.xml_declaration, encoding=self.lxml_encoding).decode(self.lxml_encoding).encode(self.encoding)


class JSONConverter(Converter):

    EMBEDDED_JSON_KEY = '__powerbi-vcs-embedded-json__'
    SORT_KEYS = False  # format seems dependent on key order which is ... odd.

    def __init__(self, encoding):
        self.encoding = encoding

    def _jsonify_embedded_json(self, v):
        """
        Some pbit json has embedded json strings. To aid readability and diffs etc., we make sure we load and format
        these too. To make sure we're aware of this, we follow the encoding:

        ```
        x: "{\"y\": 1 }"
        ```

        becomes

        ```
        x: { EMBEDDED_JSON_KEY: { "y": 1 } }
        ```
        """
        if isinstance(v, str):
            try:
                d = json.loads(v)
                if isinstance(d, (dict, list)):
                    return {self.EMBEDDED_JSON_KEY: d}
                else:
                    return v
            except Exception as e:
                return v
        elif isinstance(v, dict):
            return {kk: self._jsonify_embedded_json(vv) for kk, vv in v.items()}
        elif isinstance(v, list):
            return [self._jsonify_embedded_json(vv) for vv in v]
        else:
            return v

    def _undo_jsonify_embedded_json(self, v):
        """
        Unfo jsonify_embedded_json e.g.

        ```
        x: { EMBEDDED_JSON_KEY: { "y": 1 } }
        ```

        becomes

        ```
        x: "{\"y\": 1 }"
        ```
        """
        if isinstance(v, dict):
            if len(v) == 1 and self.EMBEDDED_JSON_KEY in v:
                return json.dumps(v[self.EMBEDDED_JSON_KEY], separators=(',', ':'), ensure_ascii=False, sort_keys=self.SORT_KEYS)
            return {kk: self._undo_jsonify_embedded_json(vv) for kk, vv in v.items()}
        elif isinstance(v, list):
            return [self._undo_jsonify_embedded_json(vv) for vv in v]
        else:
            return v

    def raw_to_vcs(self, b):
        """ Converts raw json from pbit into that ready for vcs - mainly just prettification """

        return json.dumps(self._jsonify_embedded_json(json.loads(b.decode(self.encoding))), indent=2,
                          ensure_ascii=False,  # so embedded e.g. copyright symbols don't be munged to unicode codes
                          sort_keys=self.SORT_KEYS).encode('utf-8')

    def vcs_to_raw(self, b):
        """ Converts vcs json to that used in pbit - mainly just minification """
        return json.dumps(self._undo_jsonify_embedded_json(json.loads(b.decode('utf-8'))), separators=(',', ':'), ensure_ascii=False, sort_keys=self.SORT_KEYS).encode(self.encoding)


class MetadataConverter(Converter):

    def raw_to_vcs(self, b):
        """ The metadata is nearly readable anyway, but let's just split into multiple lines """

        # repr it so bytes are displayed in ascii
        s = repr(b)

        # now split it nicely into line items
        if '\n' in s:
            raise ValueError("TODO: '\n' is used as a terminator but already exists in string! Someone needs to write some code to dynamically pick the (possibly multi-byte) terminator ...")
        splat = re.split('(\\\\x[0-9a-f]{2})([^\\\\x])', s)
        out = ''
        for i, spl in enumerate(splat):
            if i % 3 == 2:
                out += '\n'
            out += spl
        return out.encode('ascii')

    def vcs_to_raw(self, b):
        """ Undo the above prettification """

        return ast.literal_eval(b.decode('ascii').replace('\n', ''))


class DataMashupConverter(Converter):
    """
    The DataMashup file is a bit funky. The format is (roughly):
        - 4 null bytes
        - 4 bytes representing little-endian int for length of next zip
        - bytes (of length above) as zip
        - 4 bytes representing little-endian int for length of next xml
        - utf-8-sig xml of above length
        - 4 bytes representing little-endian int - which seems to be 34 more than the one two below:
        - 4 null bytes
        - 4 bytes representing little-endian int for length of next xml
        - xml of this length
        - not sure what the remainder is ...
    """

    CONVERTERS = {
        '[Content_Types].xml': XMLConverter('utf-8-sig', True),
        'Config/Package.xml': XMLConverter('utf-8-sig', True),
        'Formulas/Section1.m': NoopConverter()
    }

    def write_raw_to_vcs(self, b, outdir):
        """ Convert the raw format into multiple separate files that are more readable """

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
        with zipfile.ZipFile(BytesIO(zip1)) as zd:
            order = []
            # read items (in the order they appear in the archive)
            for name in zd.namelist():
                order.append(name)
                outfile = os.path.join(outdir, name)
                os.makedirs(os.path.dirname(outfile), exist_ok=True) # create folder if needed
                conv = self.CONVERTERS[name]
                conv.write_raw_to_vcs(zd.read(name), outfile)

        # write order:
        open(os.path.join(outdir, ".zo"), 'w').write("\n".join(order))

        # now write the xmls and bytes between:
        # open(os.path.join(outdir, 'DataMashup', "1.int"), 'wb').write(b[4:8])
        XMLConverter('utf-8-sig', True).write_raw_to_vcs(xml1, os.path.join(outdir, "3.xml"))
        XMLConverter('utf-8-sig', True).write_raw_to_vcs(xml2, os.path.join(outdir, "6.xml"))
        NoopConverter().write_raw_to_vcs(extra, os.path.join(outdir, "7.bytes"))

    def write_vcs_to_raw(self, vcs_dir, rawzip):

        # zip up the header bytes:
        b = BytesIO()
        with zipfile.ZipFile(b, mode='w', compression=zipfile.ZIP_DEFLATED) as zd:
            order = open(os.path.join(vcs_dir, ".zo")).read().split("\n")
            for name in order:
                conv = self.CONVERTERS[name]
                with zd.open(name, 'w') as z:
                    conv.write_vcs_to_raw(os.path.join(vcs_dir, name), z)

        # write header
        rawzip.write(b'\x00\x00\x00\x00')

        # write zip
        rawzip.write(struct.pack("<i", b.tell()))
        b.seek(0)
        rawzip.write(b.read())

        # write first xml:

        xmlb = XMLConverter('utf-8-sig', True).vcs_to_raw(open(os.path.join(vcs_dir, "3.xml"), 'rb').read())
        rawzip.write(struct.pack("<i", len(xmlb)))
        rawzip.write(xmlb)

        # write second xml:
        xmlb = XMLConverter('utf-8-sig', True).vcs_to_raw(open(os.path.join(vcs_dir, "6.xml"), 'rb').read())
        rawzip.write(struct.pack("<i", len(xmlb) + 34))
        rawzip.write(b'\x00\x00\x00\x00')
        rawzip.write(struct.pack("<i", len(xmlb)))
        rawzip.write(xmlb)

        # write the rest:
        NoopConverter().write_vcs_to_raw(os.path.join(vcs_dir, "7.bytes"), rawzip)
