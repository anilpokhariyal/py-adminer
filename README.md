# PyAdminer
PyAdminer is a Python based database query interface. you can manage your database and perform all the operations like read write delete and update with a user friendly interface. It's a open source project, so anyone can contribute to this with feature updates, security updates and suggestions for improvement. This project can be setup either with venv or docker. easy setup instructions for both are added in the readme.

<h4>Setting Up project</h4>
To setup project on your system, please follow these steps:

<strong>Step 1:</strong> Download repository<br>
<strong>Step 2:</strong> Activate virtual env using command: "source venv/bin/activate"
expecting you running on ubuntu, otherwise please find right command 
for your OS.<br>
<strong>Step 3:</strong> Set flask_app env by executing command: "export FLASK_APP=main.py"<br>
<strong>Step 4:</strong> Run your application by command: "FLASK run".

<strong>Note :</strong> If you want to change the port or IP on which app is running, you can update that on main.py file.
find <strong>"app.run(host="0.0.0.0", port=5000)"</strong> at bottom of main.py


<p>
  If you want to setup pyadminer in a docker environment, docker files are created for that, you can directly run setup-docker.sh file. please confirm configration before running docker container.
  </p>
