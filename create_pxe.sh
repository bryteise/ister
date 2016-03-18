#!/usr/bin/bash -x

TYPE=provision
TDIR=pxe
MDIR=/tmp/mntpxe
IMG=${TYPE}.img
PXE_NAME=clear-pxe.tar.xz
mkdir -p ${TDIR}
mkdir -p ${MDIR}
#FIXME lets not use a magic number here, this is for a 64M 
#offset but we should read it with fdisk or something.
sudo mount -o loop,ro,offset=67108864  ${IMG} ${MDIR}
sudo cp -r ${MDIR}/* ${TDIR}/
sudo umount ${MDIR}
cd ${TDIR}
sudo rm -rf boot home lib64 lost+found media mnt root srv var
ln -s /usr/lib64/ lib64
ln -s /usr/lib/systemd/systemd init
cp -a lib/kernel/org.clearlinux.native* ../
sudo find . | cpio -o -H newc | gzip > ../initrd
cd ..
XZ_OPT=-9 tar cJf ${PXE_NAME} initrd org.clearlinux.native*
sudo rm -rf ./${TDIR} ${MDIR}
sudo rm ./initrd ./org.clearlinux.native*

