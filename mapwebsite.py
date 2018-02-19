import argparse
import logging
import urllib.request
import collections
from urllib.parse import scheme_chars
import re
import queue
import threading
from bs4 import BeautifulSoup

aP = argparse.ArgumentParser(description="Scrapes web links")

aP.add_argument('url', help="url of website being scraped")

aP.add_argument('--ofilem', metavar='o', help="output to file")

aP.add_argument('--limit' , metavar='l', help="limit search to given domain")

aP.add_argument('--mulch', metavar='m', help="output only the URLs of pages within the domain and not broken", action='store_const', const=True)


IP_RE = re.compile(r'^(([0-9]|[1-9][0-9]|1[0-9]{2}|2[0-4][0-9]|25[0-5])\.){3}([0-9]|[1-9][0-9]|1[0-9]{2}|2[0-4][0-9]|25[0-5])$')

#list of known tld exceptions.
tldExceptions = ['co.uk','com','gov','net','org']
#remove the https to expose full domain
SCHEME_RE = re.compile(r'^([' + scheme_chars + ']+:)?//')

class ATag(object):
    broken = False
    def __init__(self,url):
        self.netloc = self.network_location(url)
        self.url = url
        self.build_url_attrs()

        if len(self.full_domain) == 0: #attempt resoultion
            self.full_domain = VisitCache.main_url.netloc
            self.url = 'http://' + self.full_domain + url
            self.netloc = self.network_location(self.url)
            self.build_url_attrs()

    def build_url_attrs(self):
        lower_labels = [label.lower() for label in self.netloc.split(".")]
        self.suffix_offset = find_tld(lower_labels)
        self.tld = ".".join(lower_labels[self.suffix_offset:])
        self.full_domain = ".".join(lower_labels[:self.suffix_offset])
        self.subdomain, s , self.domain = self.full_domain.rpartition(".")


    def network_location(self,url):
        return SCHEME_RE.sub("", url) \
        .partition("/")[0] \
        .partition("?")[0] \
        .partition("#")[0] \
        .split("@")[-1] \
        .partition(":")[0] \
        .strip() \
        .rstrip(".")


    def __hash__(self):
        return hash(self.url)

    def __eq__(self,other):
        return self.url == other.url

    def __repr__(self):
        return self.url +  " "

    def visit(self):
        """ return a list of urls for this page """
        VisitCache.visit_urls.add(self)
        html_page = None
        try:
            html_page = urllib.request.urlopen(self.url)
        except urllib.error.HTTPError as msg:
            req = urllib.request.Request(self.url, headers={'User-Agent' : "Love Browser"})
            html_page = urllib.request.urlopen(req)
        except Exception as msg:
            return []

        self.page_code = html_page.getcode()

        if self.page_code == 404:
            self.broken = True

        soup = BeautifulSoup(html_page, 'html.parser')
        return [ATag(a_tag['href']) for a_tag in soup.findAll('a', href=True)]



    def visit_dry(self):
        try:
            html_page = urllib.request.urlopen(self.url)
            self.page_code = html_page.getcode()
            if self.page_code == 404:
                self.broken = True
        except Exception :
            pass

        VisitCache.visit_urls.add(self)
        return []

    def mark_visit(self):
        VisitCache.visit_urls.add(self)




class VisitCache(object):
    main_url = None
    visit_urls = set()
    urls = set()
    interations = 0
    def not_visted(self,urls):
        pass

    def visited(self,urls):
        pass

    def broken(self,urls):
        pass
    @classmethod
    def print_found_urls(cls):
        for url in cls.visit_urls:
            print(url.url + " : ", "Broken? : " + str(url.broken))

    @classmethod
    def print_local_urls(cls):
        for url in cls.visit_urls:
            if url.domain == cls.main_url.domain:
                print(url.url + " : ", "Broken? : " + str(url.broken))

    @classmethod
    def print_local_not_broken(cls):
        for url in cls.visit_urls:
            if url.domain == cls.main_url.domain and not url.broken:
                print(url.url + " : ", "Broken? : " + str(url.broken))







class Crawler(object):

    def __init__(self):
        self.q = queue.Queue()
        self.e = threading.Event()
        threading.Thread(target=self.crawl_worker).start()
        threading.Thread(target=self.crawl_worker).start()
        threading.Thread(target=self.crawl_worker).start()
        threading.Thread(target=self.crawl_worker).start()

    def crawl(self):
        self.urls = set()
        for url in VisitCache.urls:
            if VisitCache.main_url.domain == url.domain:
                self.urls.update(url.visit())
            else:
                url.visit_dry()

        VisitCache.urls.update(self.urls)
        VisitCache.urls.difference_update(VisitCache.visit_urls)

        if len(VisitCache.urls) == 0:
            return
        self.crawl()

    def multi_crawl(self):
        self.urls = set()
        self.e = threading.Event()
        for url in VisitCache.urls:
            if VisitCache.main_url.domain == url.domain:
                self.q.put(url.visit)
            else:
                self.q.put(url.visit_dry)
        self.q.join()
        self.e.set()
        VisitCache.urls.update(self.urls)
        VisitCache.urls.difference_update(VisitCache.visit_urls)
        if len(VisitCache.urls) == 0:
            return
        self.multi_crawl()

    def crawl_worker(self):
        while True:
            task = self.q.get()
            if task is None:
                break
            self.urls.update(task())
            self.q.task_done()






def find_tld(lower_labels):
    for i in range(len(lower_labels)):
        possible_tld = ".".join(lower_labels[i:])
        if possible_tld in tldExceptions:
            return i

    return len(lower_labels)


if __name__ == '__main__':
    arguments = aP.parse_args()
    main_url_o = ATag(arguments.url)
    VisitCache.main_url = main_url_o
    VisitCache.urls.update([main_url_o])
    c = Crawler()
    c.multi_crawl()
    c.q.put(None)
    c.q.put(None)
    c.q.put(None)
    c.q.put(None)

    if arguments.mulch is not None:
        VisitCache.print_local_not_broken()
    else:
        VisitCache.print_found_urls()
