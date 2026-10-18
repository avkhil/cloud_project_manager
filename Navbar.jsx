import {Link} from 'react-router-dom'; import {useAuth} from '../context/AuthContext';
export default function Navbar(){const {user,logout}=useAuth();return <nav><Link className="brand" to="/">CloudVault</Link><div><span>{user.name}</span>{user.role==='ADMIN'&&<Link to="/admin">Admin</Link>}<button onClick={logout}>Logout</button></div></nav>}
