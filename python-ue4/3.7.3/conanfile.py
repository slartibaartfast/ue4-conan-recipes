from conans import AutoToolsBuildEnvironment, ConanFile, tools
import io, os

class PythonUe4Conan(ConanFile):
    name = "python-ue4"
    version = "3.7.3"
    license = "Python-2.0"
    url = "https://github.com/slartibaartfast/ue4-conan-recipes/python-ue4"
    description = "Shared CPython custom build for Unreal Engine 4"
    settings = "os", "compiler", "build_type", "arch"
    requires = ("libcxx/ue4@adamrehn/profile")
    #default_options = {"OpenSSL:shared": True}  # this caused a compiler error - configure: error: cannot run C compiled programs

    def requirements(self):
        #self.requires("OpenSSL/ue4@trota/{}".format(self.channel))  # this may not work
        self.requires("OpenSSL/1.0.2n@conan/stable")  # this worked on 4.21, need 102h for 4.22 on linux
        #self.requires("OpenSSL/ue4@adamrehn/{}".format(self.channel)) # can't import ssl error when running resulting python
        self.requires("zlib/ue4@adamrehn/{}".format(self.channel))

    def _capture(self, command):
        output = io.StringIO()
        self.run(command, output=output)
        return output.getvalue().strip()

    def source(self):
        if self.settings.os != "Windows":

            # Clone the CPython source code
            self.run("git clone --progress --depth=1 https://github.com/python/cpython.git -b v{}".format(self.version))

            # Disable the use of the getrandom() function, since this causes issues when statically linking under Linux
            tools.replace_in_file("cpython/configure", "have_getrandom=yes", "have_getrandom=no")

            # Under Linux, the UE4-bundled version of zlib is typically named libz_fPIC.a, but CPython expects libz.a
            zlibName = self.deps_cpp_info["zlib"].libs[0]
            if zlibName != "z":
                tools.replace_in_file("cpython/setup.py", "find_library_file(lib_dirs, 'z')", "find_library_file(lib_dirs, '{}')".format(zlibName))
                tools.replace_in_file("cpython/setup.py", "libraries = ['z']", "libraries = ['{}']".format(zlibName))

            # Fix the OpenSSL issues regarding missing zlib symbols that are caused by static linking
            # This is not in 3.7.2 setup.py
            # tools.replace_in_file("cpython/setup.py", "libraries = ['ssl', 'crypto']", "libraries = ['ssl', 'crypto', '{}']".format(zlibName))

    def build(self):
        if self.settings.os == "Windows":

            # TODO: retrieve and incorporate the Python development files so consumers can build native extensions

            # Under Windows we simply wrap the official embeddable distribution of CPython
            distributions = {
                "x86_64": {
                    "md5": "73df7cb2f1500ff36d7dbeeac3968711",
                    "suffix": "amd64"
                },
                "x86": {
                    "md5": "60470b4cceba52094121d43cd3f6ce3a",
                    "suffix": "win32"
                }
            }

            # Download and extract the appropriate zip file for the build architecture
            details = distributions[str(self.settings.arch)]
            url = "https://www.python.org/ftp/python/{}/python-{}-embed-{}.zip".format(self.version, self.version, details["suffix"])
            tools.get(url, md5=details["md5"], destination=self.package_folder)

        else:

            # Enable compiler interposition under Linux to enforce the correct flags for libc++
            from libcxx import LibCxx
            LibCxx.set_vars(self)

            # Build CPython from source as a shared object, so that it may be embedded
            # see https://www.gnu.org/software/autoconf-archive/ax_check_openssl.html
            # If you want a release build with all stable optimizations active (PGO, etc),
            # please run ./configure --enable-optimizations
            # Compiling --without-c-locale-coercion for UE4 4.22 changes on linux
            # and Python PEP 538
            os.chdir("cpython")
            autotools = AutoToolsBuildEnvironment(self)
            LibCxx.fix_autotools(autotools)
            #autotools.configure(args=["--enable-shared", "--with-openssl=/usr/lib/x86_64-linux-gnu"])
            autotools.configure(args=["--enable-shared", "--without-c-locale-coercion"])
            autotools.make()
            autotools.install()

    def package_info(self):
        self.cpp_info.libs = tools.collect_libs(self)

        if self.settings.os != "Windows":

            # Retrieve the list of required system libraries from the config script
            os.chdir(os.path.join(self.package_folder, "bin"))
            output = self._capture("./python3.7m-config --libs")
            libs = [lib.replace("-l", "") for lib in output.split(" ")]
            libs = [lib for lib in libs if lib not in self.cpp_info.libs + self.deps_cpp_info.libs]
            self.cpp_info.libs.extend(libs)
