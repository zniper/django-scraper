django-scraper
==============

**django-scraper** is a Django application which crawls and downloads online content following configurable instructions.

* Extract content of given online websites/pages using XPath queries.
* Automatically browse and download content in related pages, with given depth.
* Support metadata extract along with other content
* Have content refinement rules and black words filtering
* Store and prevent duplication of downloaded content
* Allow changing User Agent
* Support proxy servers

Installation
------------
This application requires some other tools installed first:
    
    lxml
    requests

**django-scraper** installation can be made using `pip`:

    pip install django-scraper
    
Configuration
-------------
In order to use **django-scraper**, it should be put into `Django` settings as installed application.
    
    INSTALLED_APPS = (
        ...
        'scraper',
    )
    
There are also some important configuration values should be added into settings file:

    CRAW_ROOT = '/path/to/local/storage'
    
Usage
-----
To start using the application, you should create new `Source` object via admin interface. There, please enter following information:
    
* `url` - URL to the start page of `source` (website, entry list,...)
* `name` - Name of the source
* `link xpath` - XPATH to links of main content page (entries, articles,...)
* `expand rules` - XPATH to url values of next scraping session ~ higher depth
* `crawl depth` - Max depth of scraping session. This relates to expand rules
* `content xpath` - XPATH to the target value of content page (article body,...)
* `content type` - Type of the current `source`
* `meta xpath` - Python dictionary of meta-data information will extracted along the main content

    *Example:*
        
        {
            'title': '//h1[@class="title"]/text()',
            'keywords': 'keywords': '//meta[@name="keywords"]/@content',
        }
* `extra xpath` - XPATH to additional content that will be downloaded (PDF files, video clips,...)
* `refine rules` - List of regular expressions will be applied to content to remove redundant data. Each regex stays in one different line.

    *Example:*
        
        <div class="tags".*$
        <br/?>

* `active` - Determine if this `source` will run or not
* `download image` - Check this to download all images present inside the specified content
* `black words` - Select set of words, a content will not be downloaded if containing one of those words
* `proxy` - Proxy server will be used when crawling current source
* `user agent` - User Agent value set in the header of every requests

After being saved, the `source` object will run a scraping session by calling crawl() method:

    source_object.crawl()

or under console, by running management command `run_scraper`:
    
    python manage.py run_scraper
    
With this command, all active sources inside current Django instance will be processed consecutively.

--
*For further information, issues, or any questions regarding this, please email to me[at]zniper.net*
