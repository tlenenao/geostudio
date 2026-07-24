# SPDX-License-Identifier: Apache-2.0
from app.harvest.connectors import ows

WMS_130 = b"""<?xml version="1.0"?>
<WMS_Capabilities version="1.3.0" xmlns="http://www.opengis.net/wms">
  <Capability>
    <Layer>
      <Title>Racine</Title>
      <Layer>
        <Name>topp:states</Name>
        <Title>USA</Title>
        <KeywordList><Keyword>census</Keyword></KeywordList>
      </Layer>
    </Layer>
  </Capability>
</WMS_Capabilities>"""

BILLION_LAUGHS = b"""<?xml version="1.0"?>
<!DOCTYPE lolz [
  <!ENTITY lol "lol">
  <!ENTITY lol2 "&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;">
  <!ENTITY lol3 "&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;">
]>
<WMS_Capabilities>&lol3;</WMS_Capabilities>"""

XXE = b"""<?xml version="1.0"?>
<!DOCTYPE foo [ <!ENTITY xxe SYSTEM "file:///etc/passwd"> ]>
<WMS_Capabilities><Title>&xxe;</Title></WMS_Capabilities>"""


def test_parse_capabilities_returns_root_element():
    root = ows.parse_capabilities(WMS_130)
    assert root is not None
    assert ows.local(root.tag) == "WMS_Capabilities"


def test_parse_capabilities_none_on_garbage():
    assert ows.parse_capabilities(b"not xml at all <<<") is None
    assert ows.parse_capabilities(b"") is None


def test_parse_capabilities_neutralises_billion_laughs():
    # Ne doit ni exploser en mémoire ni lever : retour None (entités interdites).
    assert ows.parse_capabilities(BILLION_LAUGHS) is None


def test_parse_capabilities_neutralises_xxe():
    assert ows.parse_capabilities(XXE) is None


def test_local_strips_namespace():
    assert ows.local("{http://www.opengis.net/wms}Layer") == "Layer"
    assert ows.local("Layer") == "Layer"


def test_children_and_child_text_are_namespace_agnostic():
    root = ows.parse_capabilities(WMS_130)
    capability = ows.child(root, "Capability")
    root_layer = ows.child(capability, "Layer")
    named = ows.child(root_layer, "Layer")
    assert ows.child_text(named, "Name") == "topp:states"
    assert ows.child_text(named, "Title") == "USA"
    kw_list = ows.child(named, "KeywordList")
    assert [k.text for k in ows.children(kw_list, "Keyword")] == ["census"]


def test_descendants_finds_all_matching_local_name():
    root = ows.parse_capabilities(WMS_130)
    layers = list(ows.descendants(root, "Layer"))
    assert len(layers) == 2  # racine + nommée
