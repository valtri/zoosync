#! /usr/bin/python

import sys
import unittest
from zoosync import zoosync


services = ['test-service1', 'test-service2']
names = ['TEST_SERVICE1', 'TEST_SERVICE2']
hostname = 'example-hostname'


def check_services(op = 'SERVICE', sum = 'SERVICES'):
		for s, n in zip(services, names):
			assert s in zoosync.summary[sum]
			assert '%s_%s' % (op, n) in zoosync.output
			assert zoosync.output['%s_%s' % (op, n)] == [hostname]
		assert len(services) == len(zoosync.summary[sum])


def clean_services():
	zoosync.output = {}
	zoosync.summary = {}


class TestZoosync(unittest.TestCase):

	def setUp(self):
		zoosync.setUp(sys.argv[1:])
		zoosync.services = services
		zoosync.hostname = hostname


	def tearDown(self):
		zoosync.tearDown()


	"""Initial cleanup (it should work)
	"""
	def test_00_purge(self):
		zoosync.purge()


	"""Create/remove tests (double remove should fail)
	"""
	def test_01_create(self):
		zoosync.create()
		check_services()
		clean_services()


	def test_01_get(self):
		zoosync.get(zoosync.MULTI_FIRST)
		check_services()
		clean_services()


	def test_01_create2_exception(self):
		with self.assertRaises(Exception):
			zoosync.create()
		assert 'SERVICES' not in zoosync.output


	def test_01_remove(self):
		zoosync.remove()
		check_services('REMOVED', 'REMOVED')
		clean_services()


	def test_01_remove2_exception(self):
		with self.assertRaises(Exception):
			zoosync.remove()


	"""Registration tests (double registration should work)
	"""
	def test_02_register_ok(self):
		zoosync.create(strict = False)
		check_services()
		clean_services()


	def test_02_register2_ok(self):
		zoosync.create(strict = False)
		check_services()
		clean_services()


	def test_02_register3_ok(self):
		zoosync.create(strict = False)
		check_services()
		clean_services()


	def test_03_purge(self):
		zoosync.purge()
		check_services('REMOVED', 'REMOVED')
		clean_services()


	"""(double registration should work)
	"""
	def test_03_purge2_ok(self):
		zoosync.purge()
		assert 'SERVICES' not in zoosync.output
		assert 'REMOVED' not in zoosync.output


	"""Tags tests: normal and secret tags
	"""
	def test_04_register(self):
		zoosync.create(strict = False)
		check_services()
		clean_services()


	def test_04_tag(self):
		zoosync.tag('tag1', 'value1')
		check_services('MODIFIED', 'MODIFIED')
		clean_services()


	def test_05_read_tag(self):
		zoosync.readtag('tag1')
		for s, n in zip(services, names):
			tn = 'SERVICE_%s_TAG_TAG1' % n
			assert tn in zoosync.output
			assert zoosync.output[tn] == ['value1']
		clean_services()


	def test_06_secret_tag(self):
		zoosync.tag('_secret1', 'secret-value1')
		check_services('MODIFIED', 'MODIFIED')
		clean_services()


	def test_07_read_secret_tag(self):
		zoosync.readtag('_secret1')
		for s, n in zip(services, names):
			tn = 'SERVICE_%s_TAG__SECRET1' % n
			assert tn in zoosync.output
			assert zoosync.output[tn] == ['secret-value1']
		clean_services()


	"""Tags test: unregister to see, if all the tags will survive
	""            remove to see, if tags will be removed
	"""
	def test_08_unregister(self):
		zoosync.unregister()
		check_services('REMOVED', 'REMOVED')
		clean_services()


	def test_09_register(self):
		zoosync.create(strict = False)
		check_services()
		clean_services()


	def test_10_read_tag_after(self):
		return self.test_05_read_tag()


	def test_10_read_secret_tag_after(self):
		return self.test_07_read_secret_tag()


	def test_11_remove(self):
		return self.test_01_remove()


	def test_12_no_tags(self):
		zoosync.readtag('tag1')
		assert len(zoosync.output) == 0
		zoosync.readtag('_secret1')
		assert len(zoosync.output) == 0


	"""Final cleanup
	"""
	def test_99_purge(self):
		zoosync.purge()


def suite():
	return unittest.TestLoader().loadTestsFromTestCase(TestZoosync)


if __name__ == '__main__':
	suite = suite()
	unittest.TextTestRunner(verbosity=2).run(suite)
