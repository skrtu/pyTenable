from tenable.tenable_io.base import TIOEndpoint
from tenable.utils import dict_merge
from io import BytesIO

class EditorAPI(TIOEndpoint):
    def parse_vals(self, item):
        '''
        Recursive function to attempt to pull out the various settings from
        the scan editor.
        '''
        resp = dict()
        if 'id' in item and ('default' in item
            or ('type' in item and item['type'] in [
                'file', 
                'checkbox', 
                'entry', 
                'medium-fixed-entry'])):
            # if we find both an 'id' and a 'default' attribute, or if we find
            # a 'type' attribute matching one of the known attribute types, then
            # we will parse out the data and append it to the response dictionary 
            if not 'default' in item:
                item['default'] = ""
            resp[item['id']] = item['default']

        for key in item.keys():
            # here we will attempt to recurse down both a list of sub-
            # documents and an explicitly defined sub-document within the
            # editor data-structure.
            if key == 'modes':
                continue
            if (isinstance(item[key], list) 
              and len(item[key]) > 0 
              and isinstance(item[key][0], dict)):
                for i in item[key]:
                    resp = dict_merge(resp, self.parse_vals(i))
            if isinstance(item[key], dict):
                resp = dict_merge(resp, self.parse_vals(item[key]))

        # Return the key-value pair.
        return resp

    def parse_creds(self, data):
        '''
        Walks through the credential data list and returns the configured 
        settings for a given scan policy/scan
        '''
        resp = dict()
        for dtype in data:
            for item in dtype['types']:
                if len(item['instances']) > 0:
                    for i in item['instances']:
                        # Get the settings from the inputs.
                        settings = self.parse_vals(i)
                        settings['id'] = i['id']
                        settings['summary'] = i['summary']

                        if dtype['name'] not in resp:
                            # if the Datatype doesn't exist yet, create it.
                            resp[dtype['name']] = dict()

                        if item['name'] not in resp[dtype['name']]:
                            # if the data subtype doesn't exist yet,
                            # create it. 
                            resp[dtype['name']][item['name']] = list()

                        # Add the configured settings to the key-value
                        # dictionary
                        resp[dtype['name']][item['name']].append(settings)
        return resp

    def parse_audits(self, data):
        '''
        Walks through the compliance data list and returns the configured
        settings for a given policy/scan
        '''
        resp = {
            'custom': dict(),
            'feed': dict()
        }

        for atype in data:
            for audit in atype['audits']:
                if audit['free'] == 0:
                    if audit['type'] == 'custom':
                        # if the audit is a custom-uploaded file, then we
                        # need to return the data using the format below,
                        # which appears to be how the UI sends the data.
                        fn = audit['summary'].split('File: ')[1]
                        resp['custom'].append({
                            'id': audit['id'],
                            'category': atype['name'],
                            'file': fn,
                            'variables': {
                                'file': fn,
                            }
                        })
                    else:
                        # if we're using a audit file from the feed, then
                        # we will want to pull all of the parameterized
                        # variables with the set values and store them in
                        # the variables dictionary.
                        if atype['name'] not in resp['feed']:
                            resp['feed'][atype['name']] = list()
                        resp['feed'][atype['name']].append({
                            'id': audit['id'],
                            'variables': self.parse_vals(audit)
                        })
        return resp 

    def parse_plugins(self, families, id, callfmt='editor/{id}/families/{fam}'):
        '''
        Walks through the plugin settings and will return the the configured
        settings for a given scan/policy
        '''
        resp = dict()

        for family in families:
            if families[family]['status'] != 'mixed':
                # if the plugin family is wholly enabled or disabled, then
                # all we need to set is the status.
                resp[family] = {'status': families[family]['status']}
            else:
                # if the plugin family is set to mixed, we will need to get
                # the currently enabled status of every plugin within the
                # mixed families.  To do so, we will need to query the
                # scan editor for each mixed family, getting the plugin
                # listing w/ status an interpreting that into a simple
                # dictionary of plugin_id:status.
                plugins = dict()
                plugs = self._api.get(callfmt.format(
                    id=id, fam=families[family]['id'])).json()['plugins']
                for plugin in plugs:
                    plugins[plugin['id']] = plugin['status']
                resp[family] = {
                    'mixedDefault': 'enabled',
                    'status': 'mixed',
                    'individual': plugins,
                }
        return resp

    def audits(self, etype, object_id, file_id, fobj=None):
        '''
        `editor: audits <https://cloud.tenable.com/api#/resources/editor/audits>`_

        Args:
            etype (str):
                The type of template to retrieve.  Must be either ``scan`` or
                ``policy``.
            object_od (int):
                The unique identifier of the object.
            file_id (int):
                The unique identifier of the file to export.
            fobj (FileObject):
                An optional File-like object to write the file to.  If none is
                provided a BytesIO object will be returned.

        Returns:
            FileObject: A File-like object of of the audit file.
        '''
        # If no file object was given to us, then lets create a new BytesIO
        # object to dump the data into.
        if not fobj:
            fobj = BytesIO()

        # Now we need to make the actual call.
        resp = self._api.get(
            'editor/{}/{}/audits/{}'.format(
                self._check('etype', etype, str, choices=['scan', 'policy']),
                self._check('object_id', object_id, int),
                self._check('file_id', file_id, int)
            ), stream=True)

        # Once we have made the call, stream the data into the file in 1k chunks.
        for chunk in resp.iter_content(chunk_size=1024):
            if chunk:
                fobj.write(chunk)
        fobj.seek(0)

        # lastly return the file object.
        return fobj

    def details(self, etype, uuid):
        '''
        `editor: details <https://cloud.tenable.com/api#/resources/editor/details>`_

        Args:
            etype (str):
                The type of template to retrieve.  Must be either ``scan`` or
                ``policy``.
            uuid (str):
                The UUID (unique identifier) for the template.

        Returns:
            dict: Details on the requested template
        '''
        return self._api.get(
            'editor/{}/templates/{}'.format(
                self._check('etype', etype, str, choices=['scan', 'policy']),
                self._check('uuid', uuid, str)
            )).json()

    def edit(self, etype, id):
        '''
        `editor: edit <https://cloud.tenable.com/api#/resources/editor/edit>`_

        Args:
            etype (str):
                The type of object to retrieve.  Must be either ``scan`` or
                ``policy``.
            id (int):
                The unique identifier of the object.

        Returns:
            dict: Details of the requested object
        '''
        return self._api.get(
            'editor/{}/{}'.format(
                self._check('etype', etype, str, choices=['scan', 'policy']),
                self._check('id', id, int)
            )).json()

    def list(self, etype):
        '''
        `editor: list <https://cloud.tenable.com/api#/resources/editor/list>`_

        Args:
            etype (str):
                The type of object to retrieve.  Must be either ``scan`` or
                ``policy``.

        Returns:
            list: Listing of template records.
        '''
        return self._api.get(
            'editor/{}/templates'.format(
                self._check('etype', etype, str, choices=['scan', 'policy'])
            )).json()['templates']

    def plugin_description(self, policy_id, family_id, plugin_id):
        '''
        `editor: plugin-description <https://cloud.tenable.com/api#/resources/editor/plugin-description>`_

        Args:
            policy_id (int):
                The identifier of the policy.
            family_id (int):
                The identifier of the plugin family.
            plugin_id (int):
                The identifier of the plugin within the family.

        Returns:
            dict: Details of the plugin requested.
        '''
        return self._api.get(
            'editor/policy/{}/families/{}/plugins/{}'.format(
                self._check('policy_id', policy_id, int),
                self._check('family_id', family_id, int),
                self._check('plugin_id', plugin_id, int)
            )).json()['plugindescription']