import glob
import os
import random
import unittest
import urllib.parse
from havok.useragent import agent


RESULTS = {}
URL_COUNT = 25


def queue_links(spider, response):
    soup = response.soup
    # Check links in a random order
    chase = []
    for element, attribute in [('a', 'href'), ('img', 'src'), ('script', 'src')]:
        for link in soup.findAll(element):
            if attribute in link:
                href = link[attribute]
                if not (href.startswith('http') or href.startswith('/__')
                        or href.startswith('data:') or href.startswith('mailto:')
                        or href.startswith('market:')):
                    chase.append(href)
    random.shuffle(chase)
    for url in chase:
        if url.find('#') > 0:
            url = url[:url.find('#')]
        spider.spider_test(urllib.parse.urljoin(response.url, url))
    return soup

def ignore_links(spider, response):
    return response.soup


class Spider(object):
    """
    Does two things:
        Crawls through pages looking for forms and links.
        Tests the pages by filling in the forms and loading links.
    """
    def __init__(self,
            urls=[],
            visited={},
            links=queue_links, # what does this do?
            stop_redirects=True, # passed onto agent
            host=None, # defaults to the FOST setting
        ):
        self.agent = agent(stop_redirects = stop_redirects)
        self.suite = unittest.TestSuite()
        self.pages = dict()
        if not host:
            host = 'http://localhost:8001/'
        self.host = host
        from functools import partial
        test_url = partial(urllib.parse.urljoin, host)
        for url, v in list(visited.items()):
            self.pages[test_url(url)] = v
        for url in urls:
            self.spider_test(test_url(url))
        self.links = queue_links

    def _check_page(self, url):
        self.pages.setdefault(url, dict()).setdefault('remaining', 1)

    def url_data(self, url):
        self._check_page(url)
        return self.pages[url]

    def run_suite(self):
        unittest.TextTestRunner().run(self.suite)

    def addTest(spider, url,
            data = None,
            ql = queue_links,
            url_data = None):
        if not url_data:
            url_data = spider.url_data
        if url[0]=='/':
            url = urllib.parse.urljoin(spider.host, url)
            spider._check_page(url)

        def test_process(self, response):
            soup = self.links(spider, response)
            # Look for forms to submit
            if soup and url_data(response.url).get('use_forms', True):
                for form in soup.findAll('form'):
                    spider_url_data = url_data(response.url)
                    form_id = form.get('id', form.get('name', None))
                    if form_id \
                        and 'forms' in spider_url_data \
                        and form_id in spider_url_data['forms']:
                        form_data = spider_url_data['forms'][form_id]
                    else:
                        form_data = spider_url_data
                    submit, query = build_form_query(self, form, response.url)
                    if 'data' in form_data:
                        for k, v in list(form_data['data'].items()):
                            query[k] = v
                    if submit:
                        if form.get('method', 'get').lower() == 'get':
                            spider.spider_test(
                                urllib.parse.urljoin(
                                    response.url,
                                    '%s?%s' % (
                                        form['action'],
                                        x_www_form_urlencoded(query))))
                        else:
                            self.links(spider, spider.agent.process(
                                urllib.parse.urljoin(
                                    response.url,
                                    form['action']),
                                spider_url_data,
                                x_www_form_urlencoded(query)))
        def test_runTest(self):
            if not spider.host in RESULTS:
                RESULTS[spider.host] = {}
            if url.startswith(spider.host):
                recorded_url = url[len(spider.host) - 1:]
            else:
                recorded_url = url
            try:
                self.process(spider.agent.process(url, url_data(url), data))
                RESULTS[spider.host][recorded_url] = "OK "
            except Exception as e:
                RESULTS[spider.host][recorded_url] = "ERR"
                raise

        testtype = type(str(url), (unittest.TestCase,), dict(
            process = test_process,
            runTest = test_runTest,
        ))
        def test_constructor(self, *args, **kwargs):
            super(testtype, self).__init__(*args, **kwargs)
            self.links = ql
        testtype.__init__ = test_constructor
        test = testtype()
        spider.suite.addTest(test)

    def spider_test(spider, url, data=None):
        if spider.suite.countTestCases() < URL_COUNT:
            if spider.url_data(url)['remaining']:
                spider.url_data(url)['remaining'] -= 1
                spider.addTest(url, data)

    def test_form(spider, url, form_id, data = {}, check_fn = lambda s, r: r.soup):
        response = spider.agent.process(url)
        form = response.soup.find(id=form_id)
        if not form:
            form = response.soup.find('form', form_id)
        spider.process_form(response, form, data, check_fn)

    def process_form(spider, page_response, form, data = {}, check_fn = lambda s, r: r.soup):
        assert form, page_response.soup
        submit, query = build_form_query(spider, form, page_response.url)
        for k, v in list(data.items()):
            if v is None:
                if k in query: query.pop(k)
            else:
                query[k] = v
        if form.get('method', 'get').lower() == 'get':
            response = spider.agent.process(
                urllib.parse.urljoin(page_response.url, '%s?%s' % (form['action'], x_www_form_urlencoded(query)))
            )
        elif submit:
            response = spider.agent.process(
                urllib.parse.urljoin(page_response.url, form['action']),
                {},
                x_www_form_urlencoded(query)
            )
        else:
            return None
        check_fn(spider, response)
        return response

spider_instance = Spider()


def test_response(test, response):
    if response.status_code in [301, 302, 303]:
        response_location = response['Location']
        if 'https' in response_location:
            raise Exception("Need to turn off the HTTPS middleware")
        response_location = response_location[response_location.find('/office'):]
        if '?' in response_location:
            location, qstring = response_location.split('?')
            qstring = qstring.split('&')
            query = {}
            for qpart in qstring:
                if qpart:
                    key, value = qpart.split('=')
                    query[key] = value
            print('->', location, query)
            test_response(test, test.client.get(location, query))
        else:
            print('->', response_location)
            test_response(test, test.client.get(response_location))
            print('-> POST', response_location)
            test_response(test, test.client.post(response_location))
    else:
        test.assertTrue(response.status_code in [200], "Incorrect response status of %s" % response.status_code)
    return response


def build_form_query(spider, form, base_url, form_data = {}, submit_button = None):
    query, submits, radios = {}, [], {}
    assert 'action' in form and form['action'], 'Empty action in %s' % form
    for ta in form.findAll('textarea'):
        assert 'name' in ta, '%s in %s' % (ta, base_url)
        assert len(ta.contents) <= 1, "Content of a textarea should just be some text\n" % ta.contents
        if len(ta.contents) == 1:
            [query[ta['name']]] = ta.contents

    for inp in form.findAll('input'):
        input_type = inp.get('type', 'text')
        if input_type == "submit":
            submits.append(inp)
        elif input_type == "checkbox":
            if 'checked' in inp \
                and inp.get('disabled', 'false').lower() != 'true':
                query[inp['name']] = inp.get('value', "")
        elif not input_type == "reset":
            assert 'name' in inp, '%s in %s' % (inp, base_url)
            query[inp['name']] = inp.get('value', "")

    for select in form.findAll('select'):
        assert 'name' in select, 'Select in form at %s has no name\n%s' % (base_url, select)
        options = select.findAll('option')
        assert len(options), "No options found in select at %s" % base_url
        for option in options:
            assert 'value' in option, 'No value found for option %s in select at %s' % (option, base_url)
            if option.get('selected', None):
                query[select['name']] = option['value']
        if select['name'] not in query and len(options):
            query[select['name']] = options[0]['value']
    for button in form.findAll('button'):
        submits.append(button)
    if len(submits):
        button = submits[random.randint(0, len(submits) - 1)]
        if 'name' in button:
            query[button['name']] = button['value']
        return True, query
    return False, query


def main(host=None):
    """
        This spider will start off running queries that it finds in a JSON
        configuration file.
    """
    print("Havok spider - Copyright (C) 2008-2018 Felspar Co Ltd.")
    spider = Spider(host=host, urls=['/'])
    spider.run_suite()
    with open("test.txt", "w") as res:
        hosts = list(RESULTS.keys())
        hosts.sort()
        for host in hosts:
            res.write("    %s\n" % host)
            results = list(RESULTS[host].items())
            results.sort()
            for u, e in results:
                res.write("%s %s\n" % (e, u))

