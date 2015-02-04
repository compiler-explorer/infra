#!/usr/bin/env python

import logging
import tornado.ioloop
import tornado.web
import json
import update_repo
import update_instances


class MainHandler(tornado.web.RequestHandler):
    def post(self):
        event = self.request.headers.get('X-GitHub-Event')
        obj = json.loads(self.request.body)
        logging.info("Got {}: {}".format(event, obj))
        if event == 'ping':
            logging.info("Got a ping")
            self.write("OK")
            return
	if event != 'push':
            raise RuntimeError("Unsupported")

        if 'ref' not in obj: 
            logging.info("Skipping, no ref")
            return
        if obj['repository']['name'] == 'jsbeeb':
            if obj['ref'] == 'refs/heads/master':
                update_repo.update('jsbeeb-beta')
            elif obj['ref'] == 'refs/heads/release':
                update_repo.update('jsbeeb')
            self.write("OK")
	elif obj['repository']['name'] == 'gcc-explorer':
	    if obj['ref'] == 'refs/heads/release':
		update_instances.update_gcc_explorers()
            self.write("OK")


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-8s %(module)s: %(message)s")

    application = tornado.web.Application([
        ("/", MainHandler)
    ], debug=True)
    application.listen(7453)
    tornado.ioloop.IOLoop.instance().start()
