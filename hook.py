#!/usr/bin/env python

import logging
import tornado.ioloop
import tornado.web
import json
import update_repo


class MainHandler(tornado.web.RequestHandler):
    def post(self):
        obj = json.loads(self.request.body)
        logging.info("Got {}".format(obj))
        if obj['repository']['name'] == 'jsbeeb':
            if obj['ref'] == 'refs/heads/master':
                update_repo.update('jsbeeb-beta')
            elif obj['ref'] == 'refs/heads/release':
                update_repo.update('jsbeeb')
            self.write("OK")

if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-8s %(module)s: %(message)s")

    application = tornado.web.Application([
        ("/", MainHandler)
    ], debug=True)
    application.listen(7453)
    tornado.ioloop.IOLoop.instance().start()
