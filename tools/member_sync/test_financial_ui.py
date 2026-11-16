"""Normal query navigation only selects the scoped source store."""
import pytest
from contracts import Stop
from test_source_login import login_page
from financial_ui import select_store_dialog


def test_initial_store_picker_requires_id_and_name(login_page):
    page=login_page
    html="<p>荷小悦（1581452）</p><div role='dialog'><div class='custom-modal__header'>门店选择</div><div class='group-list__item' title='1581454 荷小悦' onclick='window.selected=2'><div class='store-name'>华富世家店</div></div><div class='group-list__item' title='1581453 荷小悦' onclick='window.selected=1;this.parentElement.remove()'><div class='store-name'>紫薇壹号店</div></div></div>"
    page.evaluate('(html)=>document.body.innerHTML=html',html)
    assert select_store_dialog(page) is True
    assert page.evaluate('window.selected')==1
    assert select_store_dialog(page) is False
    page.evaluate('(html)=>document.body.innerHTML=html',html.replace('1581453','1581499'))
    with pytest.raises(Stop,match='finance_initial_store_choice_ambiguous'):select_store_dialog(page)
    page.evaluate('(html)=>document.body.innerHTML=html',html.replace('紫薇壹号店','other store'))
    with pytest.raises(Stop,match='finance_initial_store_choice_ambiguous'):select_store_dialog(page)
