from tenable.base import APIResultsIterator, APIEndpoint


class TIOEndpoint(APIEndpoint):
    def _parse_filters(self, finput, filterset, rtype='sjson'):
        '''
        A centralized method to parse and munge the filter tuples into the
        anticipates response.

        Args:
            finput (list): The list of filter tuples
            filterset (dict): The response of the allowed filters
            rtype (str, optional): 
                The filter format.  Allowed types are 'json', 'sjson', and 
                'colon'.  JSON is just a simple JSON list of dictionaries.  
                SJSON format is effectively serialized JSON into the query 
                params. COLON format denotes a colon-delimited format.

        Returns:
            dict: 
                The query parameters in the anticipated dictionary format to
                feed to requests.
        '''
        resp = dict()
        for f in finput:
            # First we need to validate the inputs are correct.  We will do that
            # by comparing the filter to the filterset data we have and compare
            # the operators and values to make sure that the input is expected.
            fname = self._check('filter_name', f[0], str)
            foper = self._check('filter_operator', f[1], str, 
                choices=filterset[f[0]]['operators'])
            fval = self._check('filter_value', f[2], str,
                choices=filterset[f[0]]['choices'],
                pattern=filterset[f[0]]['pattern'])

            if rtype == 'sjson':
                # For the serialized JSON format, we will need to generate the
                # expanded input for each filter
                i = finput.index(f)
                resp['filter.{}.filter'.format(i)] = fname
                resp['filter.{}.quality'.format(i)] = foper
                resp['filter.{}.value'.format(i)] = fval
            if rtype == 'json':
                # for standard JSON formats, we will simply build a 'filters'
                # list and store the information there.
                if 'filters' not in resp:
                    resp['filters'] = list()
                resp['filters'].append({
                    'filter': fname,
                    'quality': foper,
                    'value': fval
                })
            if rtype == 'colon':
                # for the colon-delimited format, we simply need to generate the
                # filter as NAME:OPER:VAL and dump it all into a field named f.
                if 'f' not in resp:
                    resp['f'] = list()
                resp['f'].append('{}:{}:{}'.format(fname, foper, fval))

        return resp





class TIOIterator(APIResultsIterator):
    def _get_data(self):
        '''
        Request the next page of data
        '''
        return None, None

    def _get_page(self):
        '''
        Get the next page of records
        '''
        # First we need to see if there is a page limit and if there is, have
        # we run into that limit.  If we have, then return a StopIteration
        # exception.
        if self._pages_total and self._pages_requested >= self._pages_total:
            raise StopIteration()

        # Lets make the actual call at this point.
        resp, key = self._get_data()

        # Now that we have the response, lets reset any counters we need to, 
        # and increment things like the page counter, offset, etc.
        self.page_count = 0
        self._pages_requested += 1
        self._offset += self._limit

        # Lastly we want to refresh the page data and the total based on the
        # most recent data we have.
        self.page = resp[key]
        self.total = resp['pagination']['total']