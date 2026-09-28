
Oracle error message files: *.msg
Oracle Facilities List: facilities.lis

The facility is normally the basename of the messaage file, with the suffix of 'us' stripped.

Then a messaage can be lookup up with the oerr command.

example: lookup the ORA-01027 error message:

```bash

$  oerr ora 1017
01017, 00000, "invalid credential or not authorized; logon denied"
// *Cause:  An invalid credential was provided when accessing the Oracle
//          Database or you were not authorized to access this database.
// *Action: Depending on your authentication method, ensure that the correct
//          credential is provided when logging in to Oracle Database.
//          Retry your credential after checking it. If your credential is
//          correct, you may not be authorized to access the database.
//          You will need to contact your database administrator or
//          identity management administrator to confirm that you are
//          authorized to access the database.

```

The leading zeroes in the error number are optional for lookup.

The msg files in this directory are for Oracle 26ai, but the local machine does not have 26ai, so looking up of some errors may fail.

That is not really important here.

From these error message we want to extract the error number, the description, the cause and the action.

The cause and action are optional, but the error number and description are required.

The Params and Note fields are optional, but if present, they should be extracted as well.

These are then to be put into a JSON file with the following format, using this example for ORA-01017:

If the cause or action is not present, then use 'NA' so reduce the code required to query the JSON file.

```json
{
  "error_number": "01017",
  "description": "invalid credential or not authorized; logon denied",
  "cause": "An invalid credential was provided when accessing the Oracle Database or you were not authorized to access this database.",
  "action": "Depending on your authentication method, ensure that the correct credential is provided when logging in to Oracle Database. Retry your credential after checking it. If your credential is correct, you may not be authorized to access the database. You will need to contact your database administrator or identity management administrator to confirm that you are authorized to access the database.",
  "params: "NA",
  "note: "NA",
  "remediation: "Possible remediation steps here"
}
```

A JSON file can be created for each msg file present.  These should be created in such a way that all of them may be concatinated into a single JSON file if desired.

The structure of the JSON file should be an array of error objects, like this:

```json
[
  {
    "error_number": "01017",
    "description": "invalid credential or not authorized; logon denied",
    "cause": "An invalid credential was provided when accessing the Oracle Database or you were not authorized to access this database.",
    "action": "Depending on your authentication method, ensure that the correct credential is provided when logging in to Oracle Database. Retry your credential after checking it. If your credential is correct, you may not be authorized to access the database. You will need to contact your database administrator or identity management administrator to confirm that you are authorized to access the database.",
     "params: "NA",
     "note: "NA",
    "remediation: "Possible remediation steps here"
  },
  {
    "error_number": "01018",
    "description": "another error description",
    "cause": "NA",
    "action": "NA",
    "params: "NA",
    "note: "NA",
    "remediation: "Possible remediation steps here"
  }
]
```

The remedation field is to be populated with 'NA' at this time.  A future step will be to add remediation steps for selected error messages.

When contatenating multiple JSON files, ensure that the resulting file is a valid JSON array. 

For ease of lookup, the full file should contain an array per facility, with the facility name as the key and the array of error objects as the value.  For example:

```json
{
  "ora": [
    {
      "error_number": "01017",
      "description": "invalid credential or not authorized; logon denied",
      "cause": "An invalid credential was provided when accessing the Oracle Database or you were not authorized to access this database.",
      "action": "Depending on your authentication method, ensure that the correct credential is provided when logging in to Oracle Database. Retry your credential after checking it. If your credential is correct, you may not be authorized to access the database. You will need to contact your database administrator or identity management administrator to confirm that you are authorized to access the database.",
      "params: "NA",
      "note: "NA",
      "remediation: "Possible remediation steps here"
    },
    {
      "error_number": "01018",
      "description": "another error description",
      "cause": "NA",
      "action": "NA",
      "params: "NA",
      "note: "NA",
      "remediation: "Possible remediation steps here"
    }
  ],
  "other_facility": [
    {
      "error_number": "02001",
      "description": "some other error description",
      "cause": "NA",
      "action": "NA",
      "params: "NA",
      "note: "NA",
      "remediation: "Possible remediation steps here"
    }
  ]
}
```

Create both JSON and NDJSON files for each facility. 

Provide jq queries with examples for each of the JSON file types.


If you have other suggestions, please present them.  The goal is to have a single JSON file that can be used to populate a database of some kind for easy agent lookup.

