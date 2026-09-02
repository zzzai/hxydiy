import unittest

from app.models.scrm import CustomerTag


class TestScrmTagScopeContract(unittest.TestCase):
    def test_tag_name_is_scoped_by_store_not_globally_unique(self):
        """同名画像标签必须允许存在于不同门店，隔离边界由 store_id + name 保证。"""
        self.assertFalse(CustomerTag.__table__.c.name.unique)
