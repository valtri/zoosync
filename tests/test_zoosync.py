#! /usr/bin/python

import sys
import unittest
from zoosync import zoosync


services = ['test-service1', 'test-service2']
names = ['TEST_SERVICE1', 'TEST_SERVICE2']
hostname = 'example-hostname'


def check_services(op = 'SERVICE', sum = 'SERVICES', details = True):
		for s, n in zip(services, names):
			assert s in zoosync.summary[sum]
			if details:
				assert '%s_%s' % (op, n) in zoosync.output
				assert zoosync.output['%s_%s' % (op, n)] == [hostname]
		assert len(services) == len(zoosync.summary[sum])


def clean_services():
	zoosync.output = {}
	zoosync.summary = {}


class TestZoosync(unittest.TestCase):

	@classmethod
	def setUpClass(self):
		zoosync.setUp(sys.argv[1:])
		zoosync.services = services
		zoosync.hostname = hostname
		zoosync.wait_time = 5
		zoosync.poll_interval = 1


	@classmethod
	def tearDownClass(self):
		zoosync.tearDown()


class TestZoosyncCreate(TestZoosync):

	"""Initial cleanup (it should work)
	"""
	def test_00_purge(self):
		zoosync.purge()


	"""Initial get should return missing services
	"""
	def test_01_get(self):
		zoosync.get(zoosync.MULTI_FIRST)
		check_services('MISSING', 'MISSING', details = False)
		clean_services()


	"""Create/remove tests (double remove should fail)
	"""
	def test_02_create(self):
		zoosync.create()
		check_services()
		clean_services()


	def test_03_get(self):
		zoosync.get(zoosync.MULTI_FIRST)
		check_services()
		clean_services()


	def test_04_create2_exception(self):
		with self.assertRaises(Exception):
			zoosync.create()
		assert 'SERVICES' not in zoosync.output


	def test_05_remove(self):
		zoosync.remove()
		check_services('REMOVED', 'REMOVED')
		clean_services()


	def test_06_remove2_exception(self):
		with self.assertRaises(Exception):
			zoosync.remove()


	"""Registration tests (double registration should work)
	"""
	def test_07_register_ok(self):
		zoosync.create(strict = False)
		check_services()
		clean_services()


	def test_08_register2_ok(self):
		zoosync.create(strict = False)
		check_services()
		clean_services()


	def test_09_register3_ok(self):
		zoosync.create(strict = False)
		check_services()
		clean_services()


	def test_10_purge(self):
		zoosync.purge()
		check_services('REMOVED', 'REMOVED')
		clean_services()


	"""(double registration should work)
	"""
	def test_11_purge2_ok(self):
		zoosync.purge()
		assert 'SERVICES' not in zoosync.output
		assert 'REMOVED' not in zoosync.output


class TestZoosyncTags(TestZoosync):

	def read_tag(self):
		zoosync.readtag('tag1')
		for s, n in zip(services, names):
			tn = 'SERVICE_%s_TAG_TAG1' % n
			assert tn in zoosync.output
			assert zoosync.output[tn] == ['value1']
		clean_services()


	def read_secret_tag(self):
		zoosync.readtag('_secret1')
		for s, n in zip(services, names):
			tn = 'SERVICE_%s_TAG__SECRET1' % n
			assert tn in zoosync.output
			assert zoosync.output[tn] == ['secret-value1']
		clean_services()


	"""Tags tests: normal and secret tags
	"""
	def test_01_register(self):
		zoosync.create(strict = False)
		check_services()
		clean_services()


	def test_03_tag(self):
		zoosync.tag('tag1', 'value1')
		check_services('MODIFIED', 'MODIFIED')
		clean_services()


	def test_04_read_tag(self):
		return self.read_tag()


	def test_04_secret_tag(self):
		zoosync.tag('_secret1', 'secret-value1')
		check_services('MODIFIED', 'MODIFIED')
		clean_services()


	def test_05_read_secret_tag(self):
		return self.read_secret_tag()


	"""Tags test: unregister to see, if all the tags will survive
	""            remove to see, if tags will be removed
	"""
	def test_06_unregister(self):
		zoosync.unregister()
		check_services('REMOVED', 'REMOVED')
		clean_services()


	def test_07_register(self):
		zoosync.create(strict = False)
		check_services()
		clean_services()


	def test_08_read_tag_after(self):
		return self.read_tag()


	def test_09_read_secret_tag_after(self):
		return self.read_secret_tag()


	def test_10_remove(self):
		zoosync.remove()
		check_services('REMOVED', 'REMOVED')
		clean_services()


	def test_11_no_tags(self):
		zoosync.readtag('tag1')
		assert len(zoosync.output) == 0
		zoosync.readtag('_secret1')
		assert len(zoosync.output) == 0


	"""Final cleanup
	"""
	def test_99_purge(self):
		zoosync.purge()


class TestZoosyncWait(TestZoosync):

	"""Empty wait should finish and return missing services
	"""
	def test_01_wait_empty(self):
		zoosync.wait()
		check_services('MISSING', 'MISSING', details = False)
		clean_services()


	def test_02_register(self):
		zoosync.create(strict = True)
		check_services()
		clean_services()


	def test_03_wait_registered(self):
		zoosync.wait()
		check_services()
		clean_services()


	def test_99_purge(self):
		zoosync.purge()


class TestZoosyncCleanup(TestZoosync):

	def test_01_cleanup_empty(self):
		zoosync.cleanup()
		check_services('MISSING', 'MISSING', details = False)
		clean_services()


	def test_02_register(self):
		zoosync.create(strict = True)
		check_services()
		clean_services()


	def test_01_cleanup_something(self):
		zoosync.cleanup()


	def test_99_purge(self):
		zoosync.purge()


def suite():
	return unittest.TestSuite([
		unittest.TestLoader().loadTestsFromTestCase(TestZoosyncCreate),
		unittest.TestLoader().loadTestsFromTestCase(TestZoosyncTags),
		unittest.TestLoader().loadTestsFromTestCase(TestZoosyncWait),
		unittest.TestLoader().loadTestsFromTestCase(TestZoosyncCleanup),
	])


if __name__ == '__main__':
	suite = suite()
	unittest.TextTestRunner(verbosity=2).run(suite)
