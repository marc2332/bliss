
import os.path

def getvalue(prompt = "?", default = None, query = ": "):
    if default != None and default != "":
        prompt = prompt + "[" + str(default) + "]" + query
    else:
        prompt = prompt + query

    answer = raw_input(prompt)
    if answer == "":
        answer = default
    return answer

def getnumber(prompt = "?", default = None, query = ": "):
    val = getvalue(prompt, default, query)
    try:
        val = int(val)
    except ValueError:
        try:
            val = float(val)
        except ValueError:
            val = None
    return(val)
    
def yesno(default = None, prompt = "yes/no ", query = "? "):
    yesvalues = ["yes", "YES", "Yes", "Y", "y", 1, True]
    novalues  = ["no", "NO", "No", "N", "n", 0, False]
    if default != None:
        if default in yesvalues:
            default = "Yes"
        else:
            default = "No"

    while True:
        a = getvalue(prompt, default, query)
        if a in yesvalues:
            return True
        elif a in novalues:
            return False
        else:
            print "Enter yes or no"


# ======= Files and directories =====================

def getuserhome():
    """Find user's home directory if possible.
    Otherwise raise error.

    """
    path=''
    try:
        path=os.path.expanduser("~")
    except:
        pass
    if not os.path.isdir(path):
        for evar in ('HOME', 'USERPROFILE', 'TMP'):
            try:
                path = os.environ[evar]
                if os.path.isdir(path):
                    break
            except: pass
    if path:
        return path
    else:
        raise RuntimeError('please define environment variable $HOME')



def iswritabledir(p):
    from tempfile import TemporaryFile

    if not os.path.isdir(p):
        return False
    try:
        t = TemporaryFile(dir=p)
        t.write('1')
        t.close()
    except OSError:
        return False
    else:
        return True


