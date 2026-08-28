# SPDX-License-Identifier: Apache-2.0
"""Assainissement des SVG d'icônes (SP-27, D4 + D6)."""

import pytest

from app.mapicons.svg import SvgRejected, sanitize_svg, sniff_content_type

LEGIT = (
    b'<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" '
    b'viewBox="0 0 24 24" fill="none" stroke="#1e293b" stroke-width="2">'
    b'<g><path d="M4 4 L20 20"/><circle cx="12" cy="12" r="3"/></g></svg>'
)
PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 64
GRADIENT_AND_TEXT = (
    b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">'
    b'<defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="1" '
    b'gradientUnits="userSpaceOnUse">'
    b'<stop offset="0%" stop-color="#f00"/>'
    b'<stop offset="100%" stop-color="#00f" stop-opacity="0.5"/>'
    b"</linearGradient>"
    b'<radialGradient id="r" fx="0.2" fy="0.3" spreadMethod="pad">'
    b'<stop offset="0" stop-color="#0f0"/></radialGradient></defs>'
    b'<rect width="4" height="4" fill="url(#g)"/>'
    b'<circle cx="8" cy="8" r="3" fill="url(#r)"/>'
    b'<text x="1" y="2" font-size="10" font-family="serif" font-weight="bold" '
    b'text-anchor="middle" dx="1" dy="2">Bonjour</text></svg>'
)


def test_a_legitimate_svg_keeps_its_graphics_and_geometry():
    out = sanitize_svg(LEGIT).decode()
    assert out.startswith("<svg")
    assert 'xmlns="http://www.w3.org/2000/svg"' in out
    assert 'viewBox="0 0 24 24"' in out
    assert 'd="M4 4 L20 20"' in out
    assert "<circle" in out and 'r="3"' in out
    assert 'stroke="#1e293b"' in out


def test_a_gradient_and_a_text_survive_intact():
    out = sanitize_svg(GRADIENT_AND_TEXT).decode()
    assert "<defs>" in out
    assert '<linearGradient id="g"' in out
    assert '<radialGradient id="r"' in out
    assert 'gradientUnits="userSpaceOnUse"' in out
    assert 'spreadMethod="pad"' in out and 'fx="0.2"' in out
    assert 'offset="0%"' in out and 'stop-color="#f00"' in out
    assert 'stop-opacity="0.5"' in out
    assert 'fill="url(#g)"' in out
    assert 'fill="url(#r)"' in out
    assert "<text" in out
    assert ">Bonjour<" in out
    assert 'font-size="10"' in out and 'font-family="serif"' in out
    assert 'text-anchor="middle"' in out and 'dx="1"' in out


def test_script_element_is_removed_with_its_subtree():
    out = sanitize_svg(
        b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">'
        b'<script>alert(1)</script><path d="M0 0"/></svg>'
    ).decode()
    assert "script" not in out
    assert "alert" not in out
    assert 'd="M0 0"' in out


def test_mixed_case_hostile_elements_are_removed():
    out = sanitize_svg(
        b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">'
        b'<ScRiPt>alert(1)</ScRiPt><path d="M0 0"/></svg>'
    ).decode()
    assert "cRiPt" not in out and "alert" not in out
    assert 'd="M0 0"' in out


def test_event_handler_attributes_are_removed():
    out = sanitize_svg(
        b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" onload="alert(1)">'
        b'<circle cx="1" cy="1" r="1" ONCLICK="alert(2)"/></svg>'
    ).decode()
    assert "onload" not in out.lower()
    assert "onclick" not in out.lower()
    assert "alert" not in out
    assert "<circle" in out


def test_smil_animation_elements_are_removed():
    out = sanitize_svg(
        b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">'
        b'<path d="M0 0"><animate attributeName="fill" to="red"/>'
        b'<set attributeName="onload" to="alert(1)"/></path></svg>'
    ).decode()
    assert "animate" not in out and "<set" not in out
    assert "alert" not in out
    assert 'd="M0 0"' in out


def test_use_and_symbol_are_removed():
    out = sanitize_svg(
        b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">'
        b'<symbol id="s"><path d="M0 0"/></symbol><use href="#s"/>'
        b'<path d="M1 1"/></svg>'
    ).decode()
    assert "symbol" not in out and "<use" not in out
    assert 'd="M1 1"' in out


def test_external_and_javascript_hrefs_are_removed():
    hostile = (
        b'<svg xmlns="http://www.w3.org/2000/svg" '
        b'xmlns:xlink="http://www.w3.org/1999/xlink" viewBox="0 0 24 24">'
        b'<image xlink:href="http://evil.test/x.png"/>'
        b'<a href="javascript:alert(1)"><path d="M0 0"/></a>'
        b'<path d="M2 2"/></svg>'
    )
    out = sanitize_svg(hostile).decode()
    assert "evil.test" not in out
    assert "javascript" not in out
    assert "xlink" not in out
    assert "<image" not in out
    assert 'd="M0 0"' not in out
    assert 'd="M2 2"' in out


def test_a_bare_href_is_removed():
    out = sanitize_svg(
        b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">'
        b'<path d="M0 0" href="http://evil.test/x"/></svg>'
    ).decode()
    assert "evil.test" not in out and "href" not in out
    assert 'd="M0 0"' in out


def test_a_gradient_referencing_an_external_document_loses_its_href():
    out = sanitize_svg(
        b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">'
        b'<defs><linearGradient id="g" href="https://evil.test/x.svg#g">'
        b'<stop offset="0" stop-color="#f00"/></linearGradient></defs>'
        b'<rect width="4" height="4" fill="url(#g)"/></svg>'
    ).decode()
    assert "evil.test" not in out
    assert "href" not in out
    assert '<linearGradient id="g"' in out


def test_pattern_and_filter_stay_forbidden():
    out = sanitize_svg(
        b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">'
        b'<defs><pattern id="p"><image href="http://evil.test/x"/></pattern>'
        b'<filter id="f"><feImage href="http://evil.test/y"/></filter></defs>'
        b'<rect width="4" height="4" fill="url(#p)"/></svg>'
    ).decode()
    assert "pattern" not in out
    assert "filter" not in out and "feImage" not in out
    assert "evil.test" not in out
    assert "<rect" in out


def test_an_xlink_prefix_bound_under_a_non_standard_name_is_still_stripped():
    out = sanitize_svg(
        b'<svg xmlns="http://www.w3.org/2000/svg" '
        b'xmlns:zz="http://www.w3.org/1999/xlink" viewBox="0 0 24 24">'
        b'<path d="M0 0" zz:href="http://evil.test/x"/></svg>'
    ).decode()
    assert "evil.test" not in out
    assert 'd="M0 0"' in out


def test_foreign_object_is_removed():
    hostile = (
        b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">'
        b'<foreignObject><body xmlns="http://www.w3.org/1999/xhtml">'
        b'<img src="x" onerror="alert(1)"/></body></foreignObject>'
        b'<path d="M1 1"/></svg>'
    )
    out = sanitize_svg(hostile).decode()
    assert "foreignObject" not in out
    assert "onerror" not in out
    assert 'd="M1 1"' in out


def test_url_and_scheme_bearing_attribute_values_are_removed():
    hostile = (
        b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">'
        b'<path d="M3 3" fill="url(http://evil.test/x)"/>'
        b'<rect x="0" y="0" width="4" height="4" stroke="url(#nope) #fff"/>'
        b'<circle cx="1" cy="1" r="1" fill="data:image/png;base64,AAAA"/></svg>'
    )
    out = sanitize_svg(hostile).decode()
    assert "evil.test" not in out
    assert "data:" not in out
    assert 'stroke="url' not in out
    assert 'd="M3 3"' in out
    assert "<rect" in out and 'width="4"' in out


def test_an_entity_encoded_url_is_decoded_by_the_parser_then_blocked():
    out = sanitize_svg(
        b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">'
        b'<path d="M0 0" fill="&#117;rl(http://evil.test/x)"/></svg>'
    ).decode()
    assert "evil.test" not in out
    assert "fill=" not in out
    assert 'd="M0 0"' in out


@pytest.mark.parametrize(
    ("value", "kept"),
    [
        ("url(#g)", True),
        ("URL(#g)", True),
        ("url( #g )", True),
        ("url('#g')", True),
        ("url(#g) #fff", False),
        ("url(#g) url(http://evil.test/x)", False),
        ("url(http://evil.test/x) url(#g)", False),
        ("url(https://evil.test/x.svg#g)", False),
        ("url(#)", False),
    ],
)
def test_local_url_references_are_accepted_only_in_their_exact_form(value, kept):
    payload = (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">'
        '<defs><linearGradient id="g"><stop offset="0" stop-color="#f00"/>'
        "</linearGradient></defs>"
        f'<rect width="4" height="4" fill="{value}"/></svg>'
    ).encode()
    out = sanitize_svg(payload).decode()
    rect = out.split("<rect")[1].split("/>")[0]
    assert ("fill=" in rect) is kept
    assert "evil.test" not in out


@pytest.mark.parametrize(
    ("value", "kept"),
    [("g", True), ("ok-1.2", True), ("a b", False), ("0bad", False)],
)
def test_id_values_are_charset_constrained(value, kept):
    payload = (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">'
        f'<defs><linearGradient id="{value}">'
        '<stop offset="0" stop-color="#f00"/></linearGradient></defs>'
        '<path d="M0 0"/></svg>'
    ).encode()
    out = sanitize_svg(payload).decode()
    gradient = out.split("<linearGradient")[1].split(">")[0]
    assert ("id=" in gradient) is kept


def test_text_content_cannot_inject_markup():
    out = sanitize_svg(
        b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">'
        b'<text x="0" y="0">&lt;/text&gt;&lt;script&gt;alert(1)&lt;/script&gt;</text>'
        b"</svg>"
    ).decode()
    assert "<script" not in out
    assert "&lt;script&gt;" in out


def test_style_attribute_and_style_element_are_removed():
    out = sanitize_svg(
        b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">'
        b"<style>* { background: url(javascript:alert(1)) }</style>"
        b'<path d="M2 2" style="fill:url(#x)"/></svg>'
    ).decode()
    assert "style" not in out
    assert "javascript" not in out
    assert 'd="M2 2"' in out


def test_a_nested_svg_loses_its_event_handler():
    out = sanitize_svg(
        b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">'
        b'<svg onload="alert(1)"><path d="M0 0"/></svg></svg>'
    ).decode()
    assert "onload" not in out and "alert" not in out
    assert 'd="M0 0"' in out


def test_a_cdata_section_cannot_smuggle_a_script():
    out = sanitize_svg(
        b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">'
        b'<path d="M0 0"/><text x="0" y="0">'
        b"<![CDATA[</text><script>alert(1)</script>]]></text></svg>"
    ).decode()
    assert "<script" not in out
    assert 'd="M0 0"' in out


@pytest.mark.parametrize(
    "payload",
    [
        b'<?xml version="1.0"?><!DOCTYPE svg [<!ENTITY a "aaa"><!ENTITY b "&a;&a;">]>'
        b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1 1">&b;'
        b'<path d="M0 0"/></svg>',
        b'<?xml version="1.0"?><!DOCTYPE s [<!ENTITY a SYSTEM "file:///etc/passwd">]>'
        b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1 1">&a;'
        b'<path d="M0 0"/></svg>',
        b'<?xml version="1.0"?><!DOCTYPE s [<!ENTITY % p SYSTEM "http://evil.test/p.dtd">%p;]>'
        b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1 1">'
        b'<path d="M0 0"/></svg>',
    ],
)
def test_entity_declarations_are_refused_with_an_actionable_code(payload):
    with pytest.raises(SvgRejected) as exc:
        sanitize_svg(payload)
    assert exc.value.code == "svg_entities_forbidden"
    assert "DOCTYPE" in exc.value.message


@pytest.mark.parametrize(
    "payload",
    [
        b'<?xml version="1.0" encoding="utf-8"?>\n'
        b"<!-- Generator: Adobe Illustrator 27.0 -->\n"
        b'<!DOCTYPE svg PUBLIC "-//W3C//DTD SVG 1.1//EN" '
        b'"http://www.w3.org/Graphics/SVG/1.1/DTD/svg11.dtd">\n'
        b'<svg version="1.1" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">'
        b'<path d="M0 0"/></svg>',
        b'<!DOCTYPE svg SYSTEM "http://evil.test/x.dtd">'
        b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">'
        b'<path d="M0 0"/></svg>',
    ],
)
def test_a_doctype_without_entity_declarations_is_accepted(payload):
    out = sanitize_svg(payload).decode()
    assert 'd="M0 0"' in out


def test_attlist_default_attribute_injection_is_neutralised_by_the_allowlist():
    out = sanitize_svg(
        b'<?xml version="1.0"?>'
        b'<!DOCTYPE svg [<!ATTLIST path onload CDATA "alert(1)">'
        b'<!ATTLIST path fill CDATA "url(http://evil.test/x)">]>'
        b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">'
        b'<path d="M0 0"/></svg>'
    ).decode()
    assert "onload" not in out
    assert "evil.test" not in out
    assert 'd="M0 0"' in out


def test_a_non_xml_payload_is_refused():
    with pytest.raises(SvgRejected) as exc:
        sanitize_svg(b"\x00\x01 pas du xml")
    assert exc.value.code == "svg_unparsable"


def test_a_non_svg_root_is_refused():
    with pytest.raises(SvgRejected) as exc:
        sanitize_svg(b'<html xmlns="http://www.w3.org/1999/xhtml"><body/></html>')
    assert exc.value.code == "svg_not_svg_root"


def test_an_svg_emptied_of_all_graphics_is_refused_not_stored_empty():
    with pytest.raises(SvgRejected) as exc:
        sanitize_svg(
            b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">'
            b"<script>alert(1)</script></svg>"
        )
    assert exc.value.code == "svg_no_graphics"


def test_a_path_stripped_of_its_geometry_does_not_count_as_graphics():
    with pytest.raises(SvgRejected) as exc:
        sanitize_svg(
            b'<svg xmlns="http://www.w3.org/2000/svg" '
            b'xmlns:s="http://www.w3.org/2000/svg" viewBox="0 0 24 24">'
            b'<path s:d="M0 0"/></svg>'
        )
    assert exc.value.code == "svg_no_graphics"


def test_an_empty_text_does_not_count_as_graphics():
    with pytest.raises(SvgRejected) as exc:
        sanitize_svg(
            b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">'
            b'<text x="0" y="0"></text></svg>'
        )
    assert exc.value.code == "svg_no_graphics"


def test_a_too_deeply_nested_svg_gets_its_own_code():
    payload = (
        b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">'
        + b"<g>" * 25
        + b'<path d="M0 0"/>'
        + b"</g>" * 25
        + b"</svg>"
    )
    with pytest.raises(SvgRejected) as exc:
        sanitize_svg(payload)
    assert exc.value.code == "svg_too_deep"


def test_missing_dimensions_are_derived_from_viewbox():
    out = sanitize_svg(
        b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 48 32"><path d="M0 0"/></svg>'
    ).decode()
    assert 'width="48"' in out
    assert 'height="32"' in out


@pytest.mark.parametrize(
    "view_box",
    [b"0 0 1e9 1e9", b"a b c d", b"0 0 -5 -5", b"0 0 0 0"],
)
def test_unusable_viewbox_dimensions_are_refused(view_box):
    with pytest.raises(SvgRejected) as exc:
        sanitize_svg(
            b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="'
            + view_box
            + b'"><path d="M0 0"/></svg>'
        )
    assert exc.value.code == "svg_no_dimensions"


def test_an_out_of_range_width_falls_back_to_the_viewbox():
    out = sanitize_svg(
        b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" '
        b'width="1e9" height="24"><path d="M0 0"/></svg>'
    ).decode()
    assert 'width="24"' in out and 'height="24"' in out


def test_a_px_suffixed_dimension_is_accepted_and_normalised():
    out = sanitize_svg(
        b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" '
        b'width="24px" height="24px"><path d="M0 0"/></svg>'
    ).decode()
    assert 'width="24"' in out and 'height="24"' in out


def test_an_svg_without_viewbox_or_dimensions_is_refused():
    with pytest.raises(SvgRejected) as exc:
        sanitize_svg(b'<svg xmlns="http://www.w3.org/2000/svg"><path d="M0 0"/></svg>')
    assert exc.value.code == "svg_no_dimensions"


def test_sniff_content_type_recognises_png_svg_and_nothing_else():
    assert sniff_content_type(PNG) == "image/png"
    assert sniff_content_type(LEGIT) == "image/svg+xml"
    assert sniff_content_type(b'<?xml version="1.0"?><svg xmlns="x"/>') == "image/svg+xml"
    assert sniff_content_type(b"GIF89a") is None
    assert sniff_content_type(b"") is None


def test_sniff_content_type_tolerates_a_bom_a_comment_and_a_doctype():
    assert sniff_content_type(b'<!-- hello --><svg xmlns="x"/>') == "image/svg+xml"
    assert sniff_content_type(b'\xef\xbb\xbf<svg xmlns="x"/>') == "image/svg+xml"
    assert (
        sniff_content_type(
            b'<?xml version="1.0"?>\n<!DOCTYPE svg PUBLIC "-//W3C//DTD SVG 1.1//EN" '
            b'"http://www.w3.org/Graphics/SVG/1.1/DTD/svg11.dtd">\n<svg xmlns="x"/>'
        )
        == "image/svg+xml"
    )
